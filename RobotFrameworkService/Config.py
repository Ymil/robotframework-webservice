class Config:
    class Default:
        responseformat = "json"
        taskfolder = "examples"
        variablefiles = None
        debugfile = None

    """
    Service Config as Singleton
    """
    _instance = None

    _cmd_args = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance.cmd_args = Config.Default()
        return cls._instance

    @property
    def cmd_args(self) -> str:
        return self._cmd_args

    @cmd_args.setter
    def cmd_args(self, value: str):
        self._cmd_args = value
