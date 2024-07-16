class DuplicateSourceError(Exception):
    def __init__(self, loc, title):
        self.loc = loc
        self.title = title
        super().__init__(f"Source already exists in queue: {title} ({loc})")
