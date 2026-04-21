import praw

class RedditService:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        user_agent: str,
    ):
        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent,
        )

    def get_authenticated_username(self) -> str:
        user = self._reddit.user.me()

        if user is None:
            raise RuntimeError("The authenticated Reddit user could not be retrieved.")

        return user.name