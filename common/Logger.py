import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')


class Logger:
    """
    自定义日志记录器，支持带颜色的控制台输出
    用于 SiliconFlow Key Scanner 项目
    """
    
    @staticmethod
    def info(message):
        """输出信息级别日志"""
        logging.info(str(message))

    @staticmethod
    def warning(message):
        """输出警告级别日志（黄色）"""
        logging.warning("\033[0;33m" + str(message) + "\033[0m")

    @staticmethod
    def error(message):
        """输出错误级别日志（红色，带分隔线）"""
        logging.error("\033[0;31m" + "-" * 50 + '\n| ' + str(message) + "\033[0m" + "\n" + "└" + "-" * 80)

    @staticmethod
    def debug(message):
        """输出调试级别日志（灰色）"""
        logging.debug("\033[0;37m" + str(message) + "\033[0m")


# 创建全局日志记录器实例
logger = Logger()
