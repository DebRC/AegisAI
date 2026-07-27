import argparse

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models import Role, User, UserRole
from app.security.permissions import SYSTEM_ADMIN_ROLE_NAME


def assign_administrator(email: str) -> bool:
    """Assign the seeded administrator role to an existing user once."""

    db = SessionLocal()

    try:
        user = db.scalar(select(User).where(User.email == email))

        if user is None:
            raise ValueError(f"No user exists with email '{email}'.")

        administrator_role = db.scalar(
            select(Role).where(Role.name == SYSTEM_ADMIN_ROLE_NAME)
        )

        if administrator_role is None:
            raise ValueError(
                "The administrator role is missing. Apply Alembic migrations first."
            )

        assignment = db.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == administrator_role.id,
            )
        )

        if assignment is not None:
            return False

        db.add(UserRole(user_id=user.id, role_id=administrator_role.id))
        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign the administrator role to an existing AegisAI user."
    )
    parser.add_argument("email", help="Registered email address to promote")
    args = parser.parse_args()

    try:
        assigned = assign_administrator(args.email)
    except ValueError as error:
        parser.error(str(error))

    if assigned:
        print(f"Administrator role assigned to {args.email}.")
    else:
        print(f"{args.email} already has the administrator role.")


if __name__ == "__main__":
    main()
