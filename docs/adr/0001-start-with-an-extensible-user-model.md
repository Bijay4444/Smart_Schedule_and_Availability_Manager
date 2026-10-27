# Start with an extensible Django user model

Use `accounts.User`, a field-free subclass of Django's `AbstractUser`, with
Django's standard session authentication. This adds a small app and migration
now while preserving the standard username/password behavior; it avoids the
cost of swapping an already-referenced user table if future account fields
are needed. Django explains this trade-off in its
[custom user model guidance](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#using-a-custom-user-model-when-starting-a-project).
