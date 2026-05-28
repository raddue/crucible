"""User-lookup module — no caching yet (intentional for b4)."""


def lookup_user(user_id):
    # placeholder: real DB lookup in production
    return {"id": user_id, "email": f"user{user_id}@example.com"}
