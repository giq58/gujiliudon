 import quote, urlencode
import sqlite3
from pathlib import Path
import requests
from dataclasses import dataclass

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scanner.log')
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ScanResult:
    """扫描结果数据类"""
    repo_full_name: str
    file_path: str
    file_sha: str
    api_key: str
    raw_url: str
    commit_sha: str
    last_modified: str
    is_valid: Optional[bool] = None
    error_message: Optional[str] = None
    quota_info: Optional[Dict] = None

class SiliconFlowValidator:
    """SiliconFlow API密钥验证器"""
    
    def __init__(self, model: str = "Qwen/Qwen2.5-7B-Instruct", proxy: Optional[str] = None):
        self.base_url = "https://api.siliconflow.cn/v1"
        self.model = model
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.session = requests.Session()
        if proxy:
            self.session.proxies.update(self.proxies)
    
    def validate_key(self, api_key: str) -> Dict[str, Any]:
        """验证SiliconFlow API密钥"""
        if not api_key.startswith("sk-"):
            return {
                "is_valid": False,
                "error_message": "Invalid key format: must start with 'sk-'",
                "response_data": None,
                "rate_limited": False
            }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SiliconFlow-Key-Scanner/1.0"
        }
        
        test_data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Hello, test message for key validation."}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=test_data,
                timeout=30
            )
            
            if response.status_code == 200:
                return {
                    "is_valid": True,
                    "error_message": None,
                    "response_data": response.json(),
                    "rate_limited": False
                }
            elif response.status_code == 401:
                return {
                    "is_valid": False,
                    "error_message": "Unauthorized: Invalid API key",
                    "response_data": None,
                    "rate_limited": False
                }
            elif response.status_code == 429:
                return {
                    "is_valid": True,  # 密钥有效，但达到速率限制
                    "error_message": "Rate limited",
                    "response_data": None,
                    "rate_limited": True
                }
            elif response.status_code == 403:
                return {
                    "is_valid": False,
                    "error_message": "Forbidden: Access denied",
                    "response_data": None,
                    "rate_limited": False
                }
            else:
                return {
                    "is_valid": False,
                    "error_message": f"HTTP {response.status_code}: {response.text}",
                    "response_data": None,
                    "rate_limited": False
                }
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout validating key: {api_key[:10]}...")
            return {
                "is_valid": False,
                "error_message": "Request timeout",
                "response_data": None,
                "rate_limited": False
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for key validation: {e}")
            return {
                "is_valid": False,
                "error_message": f"Request failed: {str(e)}",
                "response_data": None,
                "rate_limited": False
            }
    
    def check_key_quota(self, api_key: str) -> Dict[str, Any]:
        """检查API密钥配额信息"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # 尝试获取模型列表作为配额检查
            response = self.session.get(
                f"{self.base_url}/models",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                models_data = response.json()
                return {
                    "has_quota": True,
                    "quota_info": {
                        "models_available": len(models_data.get("data", [])),
                        "models_list": [model.get("id") for model in models_data.get("data", [])[:5]],  # 只显示前5个
                        "timestamp": datetime.now().isoformat()
                    },
                    "error_message": None
                }
            else:
                return {
                    "has_quota": False,
                    "quota_info": None,
                    "error_message": f"HTTP {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Quota check failed: {e}")
            return {
                "has_quota": False,
                "quota_info": None,
                "error_message": str(e)
            }

class GitHubScanner:
    """GitHub仓库扫描器"""
    
    def __init__(self):
        # 从环境变量读取配置
        self.github_tokens = os.getenv('GITHUB_TOKENS', '').split(',')
        self.github_tokens = [token.strip() for token in self.github_tokens if token.strip()]
        
        if not self.github_tokens:
            raise ValueError("GITHUB_TOKENS environment variable is required")
        
        # 配置参数
        self.data_path = Path(os.getenv('DATA_PATH', './data'))
        self.queries_file = os.getenv('QUERIES_FILE', 'queries.txt')
        self.date_range_days = int(os.getenv('DATE_RANGE_DAYS', '730'))
        self.proxy_list = [p.strip() for p in os.getenv('PROXY', '').split(',') if p.strip()]
        
        # 文件路径配置
        self.valid_key_prefix = os.getenv('VALID_KEY_PREFIX', 'keys/keys_valid_siliconflow_')
        self.rate_limited_key_prefix = os.getenv('RATE_LIMITED_KEY_PREFIX', 'keys/key_429_siliconflow_')
        self.keys_send_prefix = os.getenv('KEYS_SEND_PREFIX', 'keys/keys_send_siliconflow_')
        self.valid_key_detail_prefix = os.getenv('VALID_KEY_DETAIL_PREFIX', 'logs/keys_valid_detail_siliconflow_')
        self.rate_limited_key_detail_prefix = os.getenv('RATE_LIMITED_KEY_DETAIL_PREFIX', 'logs/key_429_detail_siliconflow_')
        self.scanned_shas_file = os.getenv('SCANNED_SHAS_FILE', 'scanned_shas_siliconflow.txt')
        
        # 文件路径黑名单
        blacklist_str = os.getenv('FILE_PATH_BLACKLIST', 
                                  'readme,docs,doc/,.md,example,sample,tutorial,test,spec,demo,mock')
        self.file_path_blacklist = [item.strip().lower() for item in blacklist_str.split(',')]
        
        # SiliconFlow密钥正则表达式 - 匹配sk-开头的密钥
        self.api_key_pattern = re.compile(r'sk-[A-Za-z0-9]{20,}')
        
        # 创建必要的目录
        self.ensure_directories()
        
        # 初始化验证器
        model = os.getenv('HAJIMI_CHECK_MODEL', 'Qwen/Qwen2.5-7B-Instruct')
        proxy = self.proxy_list[0] if self.proxy_list else None
        self.validator = SiliconFlowValidator(model=model, proxy=proxy)
        
        # 初始化数据库
        self.init_database()
        
        # 加载已扫描的SHA
        self.scanned_shas = self.load_scanned_shas()
        
        # GitHub API相关
        self.current_token_index = 0
        self.github_session = aiohttp.ClientSession()
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        directories = [
            self.data_path,
            self.data_path / 'keys',
            self.data_path / 'logs',
            self.data_path / 'db'
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def init_database(self):
        """初始化SQLite数据库"""
        db_path = self.data_path / 'db' / 'siliconflow_keys.db'
        self.conn = sqlite3.connect(str(db_path))
        
        # 创建表
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key TEXT UNIQUE NOT NULL,
                repo_full_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_sha TEXT NOT NULL,
                raw_url TEXT NOT NULL,
                commit_sha TEXT,
                last_modified TEXT,
                is_valid BOOLEAN,
                rate_limited BOOLEAN DEFAULT 0,
                error_message TEXT,
                quota_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                validated_at TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def load_scanned_shas(self) -> Set[str]:
        """加载已扫描的文件SHA列表"""
        sha_file = self.data_path / self.scanned_shas_file
        if sha_file.exists():
            try:
                with open(sha_file, 'r') as f:
                    return set(line.strip() for line in f if line.strip())
            except Exception as e:
                logger.warning(f"Failed to load scanned SHAs: {e}")
        return set()
    
    def save_scanned_sha(self, sha: str):
        """保存已扫描的文件SHA"""
        self.scanned_shas.add(sha)
        sha_file = self.data_path / self.scanned_shas_file
        try:
            with open(sha_file, 'a') as f:
                f.write(f"{sha}\n")
        except Exception as e:
            logger.error(f"Failed to save scanned SHA: {e}")
    
    def load_queries(self) -> List[str]:
        """加载搜索查询配置"""
        queries = []
        
        # 默认SiliconFlow搜索查询
        default_queries = [
            'sk- in:file',
            '"sk-" in:file filename:.env',
            '"sk-" in:file filename:config',
            '"sk-" in:file filename:.json',
            '"sk-" in:file filename:.yaml',
            'api.siliconflow.cn in:file',
            '"api.siliconflow.cn" in:file',
            'siliconflow in:file extension:env',
            '"sk-" "siliconflow" in:file',
            '"sk-" "api.siliconflow.cn" in:file',
            'SILICONFLOW_API_KEY in:file',
            'SILICON_FLOW_KEY in:file'
        ]
        
        # 尝试从文件加载
        try:
            if os.path.exists(self.queries_file):
                with open(self.queries_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            queries.append(line)
            
            if not queries:
                logger.info("No queries found in file, using default SiliconFlow queries")
                queries = default_queries
                
        except Exception as e:
            logger.error(f"Failed to load queries from {self.queries_file}: {e}")
            logger.info("Using default SiliconFlow queries")
            queries = default_queries
        
        logger.info(f"Loaded {len(queries)} search queries")
        return queries
    
    def get_current_token(self) -> str:
        """获取当前的GitHub令牌"""
        token = self.github_tokens[self.current_token_index]
        self.current_token_index = (self.current_token_index + 1) % len(self.github_tokens)
        return token
    
    def should_skip_file(self, file_path: str) -> bool:
        """判断是否应该跳过某个文件"""
        file_path_lower = file_path.lower()
        
        for blacklist_item in self.file_path_blacklist:
            if blacklist_item in file_path_lower:
                return True
        
        return False
    
    async def search_github_code(self, query: str, per_page: int = 100) -> List[Dict]:
        """搜索GitHub代码"""
        results = []
        page = 1
        max_pages = 10  # 限制最大页数
        
        # 添加日期范围过滤
        date_filter = (datetime.now() - timedelta(days=self.date_range_days)).strftime('%Y-%m-%d')
        enhanced_query = f"{query} pushed:>{date_filter}"
        
        while page <= max_pages:
            try:
                token = self.get_current_token()
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'SiliconFlow-Key-Scanner/1.0'
                }
                
                params = {
                    'q': enhanced_query,
                    'per_page': per_page,
                    'page': page
                }
                
                url = f"https://api.github.com/search/code?{urlencode(params)}"
                
                async with self.github_session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('items', [])
                        
                        if not items:
                            break
                        
                        results.extend(items)
                        
                        # 检查是否还有更多结果
                        if len(items) < per_page:
                            break
                        
                        page += 1
                        
                        # API速率限制处理
                        await asyncio.sleep(1)
                        
                    elif response.status == 403:
                        logger.warning("GitHub API rate limit exceeded, waiting...")
                        await asyncio.sleep(60)
                        continue
                    elif response.status == 422:
                        logger.warning(f"Invalid query: {enhanced_query}")
                        break
                    else:
                        logger.error(f"GitHub API error: {response.status}")
                        break
                        
            except Exception as e:
                logger.error(f"Error searching GitHub: {e}")
                await asyncio.sleep(5)
                break
        
        logger.info(f"Found {len(results)} results for query: {query}")
        return results
    
    async def get_file_content(self, raw_url: str) -> Optional[str]:
        """获取文件内容"""
        try:
            proxy = random.choice(self.proxy_list) if self.proxy_list else None
            connector = aiohttp.TCPConnector()
            
            async with aiohttp.ClientSession(connector=connector) as session:
                proxy_url = proxy if proxy else None
                async with session.get(raw_url, proxy=proxy_url, timeout=30) as response:
                    if response.status == 200:
                        content = await response.text()
                        return content
                    else:
                        logger.warning(f"Failed to fetch file content: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error fetching file content from {raw_url}: {e}")
            return None
    
    def extract_api_keys(self, content: str) -> List[str]:
        """从文件内容中提取SiliconFlow API密钥"""
        if not content:
            return []
        
        # 查找所有匹配的密钥
        matches = self.api_key_pattern.findall(content)
        
        # 去重并过滤
        unique_keys = []
        seen = set()
        
        for key in matches:
            if key not in seen and len(key) >= 25:  # 确保密钥长度合理
                seen.add(key)
                unique_keys.append(key)
        
        return unique_keys
    
    def validate_and_save_key(self, result: ScanResult) -> bool:
        """验证并保存API密钥"""
        try:
            # 验证密钥
            validation_result = self.validator.validate_key(result.api_key)
            
            result.is_valid = validation_result['is_valid']
            result.error_message = validation_result.get('error_message')
            
            # 如果密钥有效，检查配额
            if result.is_valid:
                quota_result = self.validator.check_key_quota(result.api_key)
                result.quota_info = quota_result.get('quota_info')
            
            # 保存到数据库
            self.save_to_database(result, validation_result.get('rate_limited', False))
            
            # 保存到文件
            self.save_to_files(result, validation_result.get('rate_limited', False))
            
            return result.is_valid
            
        except Exception as e:
            logger.error(f"Error validating key {result.api_key[:10]}...: {e}")
            result.error_message = str(e)
            return False
    
    def save_to_database(self, result: ScanResult, rate_limited: bool):
        """保存结果到数据库"""
        try:
            quota_info_json = json.dumps(result.quota_info) if result.quota_info else None
            
            self.conn.execute('''
                INSERT OR REPLACE INTO api_keys 
                (api_key, repo_full_name, file_path, file_sha, raw_url, commit_sha, 
                 last_modified, is_valid, rate_limited, error_message, quota_info, validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.api_key, result.repo_full_name, result.file_path, result.file_sha,
                result.raw_url, result.commit_sha, result.last_modified, result.is_valid,
                rate_limited, result.error_message, quota_info_json, datetime.now().isoformat()
            ))
            
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
    
    def save_to_files(self, result: ScanResult, rate_limited: bool):
        """保存结果到文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        try:
            # 确定文件前缀
            if result.is_valid and not rate_limited:
                key_prefix = self.valid_key_prefix
                detail_prefix = self.valid_key_detail_prefix
            elif rate_limited:
                key_prefix = self.rate_limited_key_prefix
                detail_prefix = self.rate_limited_key_detail_prefix
            else:
                return  # 无效密钥不保存到文件
            
            # 保存密钥到简单文件
            key_file = self.data_path / f"{key_prefix}{timestamp}.txt"
            with open(key_file, 'a', encoding='utf-8') as f:
                f.write(f"{result.api_key}\n")
            
            # 保存详细信息
            detail_file = self.data_path / f"{detail_prefix}{timestamp}.log"
            detail_info = {
                "timestamp": datetime.now().isoformat(),
                "api_key": result.api_key,
                "repo_full_name": result.repo_full_name,
                "file_path": result.file_path,
                "raw_url": result.raw_url,
                "is_valid": result.is_valid,
                "rate_limited": rate_limited,
                "error_message": result.error_message,
                "quota_info": result.quota_info
            }
            
            with open(detail_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(detail_info, ensure_ascii=False) + "\n")
            
        except Exception as e:
            logger.error(f"Error saving to files: {e}")
    
    async def process_search_result(self, item: Dict) -> int:
        """处理搜索结果项"""
        try:
            file_sha = item.get('sha')
            if file_sha in self.scanned_shas:
                return 0
            
            file_path = item.get('path', '')
            if self.should_skip_file(file_path):
                logger.debug(f"Skipping blacklisted file: {file_path}")
                return 0
            
            # 获取文件内容
            raw_url = item.get('html_url', '').replace('/blob/', '/raw/')
            content = await self.get_file_content(raw_url)
            
            if not content:
                return 0
            
            # 提取API密钥
            api_keys = self.extract_api_keys(content)
            if not api_keys:
                self.save_scanned_sha(file_sha)
                return 0
            
            valid_count = 0
            
            # 处理每个找到的密钥
            for api_key in api_keys:
                result = ScanResult(
                    repo_full_name=item.get('repository', {}).get('full_name', ''),
                    file_path=file_path,
                    file_sha=file_sha,
                    api_key=api_key,
                    raw_url=raw_url,
                    commit_sha=item.get('sha', ''),
                    last_modified=item.get('repository', {}).get('updated_at', '')
                )
                
                # 验证并保存密钥
                if self.validate_and_save_key(result):
                    valid_count += 1
                    logger.info(f"✅ Valid SiliconFlow key found: {api_key[:15]}... from {result.repo_full_name}/{file_path}")
                else:
                    logger.warning(f"❌ Invalid key: {api_key[:15]}... from {result.repo_full_name}/{file_path}")
                
                # 添加延迟避免过快验证
                await asyncio.sleep(2)
            
            self.save_scanned_sha(file_sha)
            return valid_count
            
        except Exception as e:
            logger.error(f"Error processing search result: {e}")
            return 0
    
    async def run_scan(self):
        """运行扫描"""
        logger.info("�� Starting SiliconFlow API key scan...")
        
        queries = self.load_queries()
        total_valid_keys = 0
        total_processed = 0
        
        try:
            for i, query in enumerate(queries, 1):
                logger.info(f"�� Processing query {i}/{len(queries)}: {query}")
                
                # 搜索GitHub
                search_results = await self.search_github_code(query)
                
                if not search_results:
                    logger.info(f"No results found for query: {query}")
                    continue
                
                # 处理搜索结果
                for item in search_results:
                    valid_keys = await self.process_search_result(item)
                    total_valid_keys += valid_keys
                    total_processed += 1
                    
                    # 每处理一定数量后输出统计
                    if total_processed % 50 == 0:
                        logger.info(f"�� Progress: {total_processed} files processed, {total_valid_keys} valid keys found")
                
                # 查询间隔
                await asyncio.sleep(5)
            
            logger.info(f"�� Scan completed! Processed: {total_processed}, Valid keys found: {total_valid_keys}")
            
        except KeyboardInterrupt:
            logger.info("⛔ Scan interrupted by user")
        except Exception as e:
            logger.error(f"❌ Scan failed: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """清理资源"""
        try:
            await self.github_session.close()
            self.conn.close()
            if hasattr(self.validator, 'session'):
                self.validator.session.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

def main():
    """主函数"""
    try:
        scanner = GitHubScanner()
        asyncio.run(scanner.run_scan())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error(f"Program failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
