"""业务层可预期异常。"""


class BusinessError(RuntimeError):
    """可向CLI返回的业务错误，不包含数据库密码或SQL内部细节。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
