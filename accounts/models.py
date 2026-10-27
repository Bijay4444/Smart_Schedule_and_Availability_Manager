from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Standard Django user, with an extension point for future account fields."""
