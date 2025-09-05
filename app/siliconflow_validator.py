import requests
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SiliconFlowValidator:
    """SiliconFlow API密钥验证器"""
    
    def __init__(self, model: str = "Qwen/Qwen2.5-7B-Instruct", proxy: Optional[str] = None):
        self.base_url = "https://api.siliconflow.cn/v1"
        self.model = model
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
    
    def validate_key(self, api_key: str) -> Dict[str, Any]:
        """
        验证SiliconFlow API密钥
        
        Args:
            api_key: API密钥
            
        Returns:
            dict: 验证结果，包含is_valid, error_message, response_data
        """
        if not api_key.startswith("sk-"):
            return {
                "is_valid": False,
                "error_message": "Invalid key format: must start with 'sk-'",
                "response_data": None
            }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 测试数据
        test_data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 10,
            "temperature": 0.7
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=test_data,
                timeout=30,
                proxies=self.proxies
            )
            
            if response.status_code == 200:
                return {
                    "is_valid": True,
                    "error_message": None,
                    "response_data": response.json()
                }
            elif response.status_code == 401:
                return {
                    "is_valid": False,
                    "error_message": "Invalid API key",
                    "response_data": None
                }
            elif response.status_code == 429:
                return {
                    "is_valid": True,  # 密钥有效，但达到速率限制
                    "error_message": "Rate limited",
                    "response_data": None
                }
            else:
                return {
                    "is_valid": False,
                    "error_message": f"HTTP {response.status_code}: {response.text}",
                    "response_data": None
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for key validation: {e}")
            return {
                "is_valid": False,
                "error_message": f"Request failed: {str(e)}",
                "response_data": None
            }
    
    def check_key_quota(self, api_key: str) -> Dict[str, Any]:
        """
        检查API密钥配额信息（如果SiliconFlow支持）
        
        Args:
            api_key: API密钥
            
        Returns:
            dict: 配额信息
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            # 尝试获取账户信息
            response = requests.get(
                f"{self.base_url}/models",  # 获取模型列表作为简单验证
                headers=headers,
                timeout=30,
                proxies=self.proxies
            )
            
            if response.status_code == 200:
                return {
                    "has_quota": True,
                    "quota_info": response.json(),
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
