import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import authenticate_user
from app.extensions import db
from app.models import Resource, User
from app.seed import (
    DEV_PASSWORD,
    DEV_USERS,
    seed_dev_users,
    seed_dev_users_command,
    seed_inventory,
    seed_inventory_command,
)


def test_seed_inventory_creates_all_resources(app):
    seed_inventory()
    db.session.commit()

    resources = Resource.query.all()

    assert len(resources) == 7
    assert {resource.type for resource in resources} == set(Resource.type.type.enums)


def test_seed_inventory_is_idempotent(app):
    seed_inventory()
    db.session.commit()
    seed_inventory()
    db.session.commit()

    resources = Resource.query.all()

    assert len(resources) == 7
    assert len({resource.type for resource in resources}) == 7


def test_seed_inventory_keeps_existing_resource(app):
    db.session.add(Resource(type="heat", name="Heat pack", total_quantity=2))
    db.session.commit()

    created = seed_inventory()
    db.session.commit()

    heat = Resource.query.filter_by(type="heat").one()

    assert heat.name == "Heat pack"
    assert heat.total_quantity == 2
    assert len(created) == 6
    assert Resource.query.count() == 7


def test_seed_inventory_command_seeds_database(app):
    result = app.test_cli_runner().invoke(seed_inventory_command)

    assert result.exit_code == 0
    assert len(result.output.strip().splitlines()) == 7
    assert "bed, Bed, 7" in result.output

    db.session.rollback()

    assert Resource.query.count() == 7


def test_seed_inventory_command_skips_existing_inventory(app):
    runner = app.test_cli_runner()
    runner.invoke(seed_inventory_command)

    result = runner.invoke(seed_inventory_command)

    assert result.exit_code == 0
    assert "Inventory already seeded" in result.output

    db.session.rollback()

    assert Resource.query.count() == 7


def test_seed_inventory_command_fails_on_integrity_error(app):
    db.session.add(Resource(type="ice_bath", name="Bed", total_quantity=3))
    db.session.commit()

    result = app.test_cli_runner().invoke(seed_inventory_command)

    assert result.exit_code == 1
    assert "seed-inventory failed" in result.output
    assert Resource.query.count() == 1


def test_seed_inventory_raises_on_duplicate_name(app):
    db.session.add(Resource(type="ice_bath", name="Bed", total_quantity=3))
    db.session.commit()

    with pytest.raises(IntegrityError):
        seed_inventory()
        db.session.commit()

    db.session.rollback()


def test_seed_dev_users_creates_all_users(app):
    created = seed_dev_users()
    db.session.commit()

    users = User.query.all()
    expected_emails = {dev_user["email"] for dev_user in DEV_USERS}

    assert len(created) == 6
    assert len(users) == 6
    assert {user.email for user in users} == expected_emails
    assert sorted(user.role for user in users) == ["client"] * 4 + ["physio"] * 2


def test_seed_dev_users_is_idempotent(app):
    seed_dev_users()
    db.session.commit()
    created = seed_dev_users()
    db.session.commit()

    assert created == []
    assert User.query.count() == 6


def test_seed_dev_users_keeps_existing_user(app):
    db.session.add(
        User(
            name="Manual physio",
            email="test_physio1@example.com",
            password_hash="manual-hash",
            role="physio",
        )
    )
    db.session.commit()

    created = seed_dev_users()
    db.session.commit()

    existing = User.query.filter_by(email="test_physio1@example.com").one()

    assert existing.name == "Manual physio"
    assert existing.password_hash == "manual-hash"
    assert len(created) == 5
    assert User.query.count() == 6


def test_seed_dev_users_raises_key_error_on_missing_key(app, monkeypatch):
    invalid_users = [{"name": "Test_bad", "email": "bad@example.com"}]
    monkeypatch.setattr("app.seed.DEV_USERS", invalid_users)

    with pytest.raises(KeyError):
        seed_dev_users()

    assert User.query.count() == 0


def test_seed_dev_users_normalizes_email(app, monkeypatch):
    messy_users = [
        {
            "name": "Test_messy",
            "email": "  Test_Messy@Example.COM ",
            "role": "client",
        }
    ]
    monkeypatch.setattr("app.seed.DEV_USERS", messy_users)

    seed_dev_users()
    db.session.commit()
    created = seed_dev_users()
    db.session.commit()

    user = User.query.one()

    assert user.email == "test_messy@example.com"
    assert created == []


def test_seeded_users_can_authenticate(app):
    seed_dev_users()
    db.session.commit()

    for dev_user in DEV_USERS:
        user = authenticate_user(dev_user["email"], DEV_PASSWORD)

        assert user is not None
        assert user.role == dev_user["role"]

    assert authenticate_user(" Test_Client1@Example.com ", DEV_PASSWORD) is not None
    assert authenticate_user("test_client1@example.com", "wrong-password") is None


def test_seed_dev_users_command_seeds_database(app):
    app.config["ENABLE_DEV_SEED"] = True

    result = app.test_cli_runner().invoke(seed_dev_users_command)

    assert result.exit_code == 0
    assert len(result.output.strip().splitlines()) == 6
    assert "physio, Test_physio1, test_physio1@example.com" in result.output

    db.session.rollback()

    assert User.query.count() == 6
    for user in User.query.all():
        assert user.password_hash not in result.output


def test_seed_dev_users_command_skips_existing_users(app):
    app.config["ENABLE_DEV_SEED"] = True
    runner = app.test_cli_runner()
    runner.invoke(seed_dev_users_command)

    result = runner.invoke(seed_dev_users_command)

    assert result.exit_code == 0
    assert "Users already seeded" in result.output

    db.session.rollback()

    assert User.query.count() == 6


def test_seed_dev_users_command_is_blocked_without_flag(app):
    result = app.test_cli_runner().invoke(seed_dev_users_command)

    assert result.exit_code == 1
    assert "ENABLE_DEV_SEED" in result.output

    db.session.rollback()

    assert User.query.count() == 0


def test_seed_dev_users_command_rolls_back_on_database_error(app, monkeypatch):
    app.config["ENABLE_DEV_SEED"] = True

    def raise_database_error():
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(db.session, "commit", raise_database_error)

    result = app.test_cli_runner().invoke(seed_dev_users_command)

    assert result.exit_code == 1
    assert "seed-dev-users failed" in result.output
    assert User.query.count() == 0
