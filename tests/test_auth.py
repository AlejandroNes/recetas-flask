"""Authentication, CSRF protection and authorization boundaries."""

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select

from practica_flask.user.models import User


def token(response):
    return BeautifulSoup(response.data, "html.parser").select_one(
        "input[name=csrf_token]"
    )["value"]


def test_register_login_logout(client, db):
    response = client.post(
        "/register/",
        data={"username": "Ana", "password": "secreto123", "confirm": "secreto123"},
        follow_redirects=True,
    )
    assert "Cuenta creada" in response.text
    user = db.session.scalar(select(User))
    assert user.username == "ana" and user.password_hash != "secreto123"
    assert user.check_password("secreto123") and not user.check_password("incorrecta")
    response = client.post(
        "/login/",
        data={"username": "ANA", "password": "secreto123"},
        follow_redirects=True,
    )
    assert "Tu cocina, en orden." in response.text
    assert client.post("/logout/").status_code == 302
    assert "/login/" in client.get("/cocina/").location


def test_duplicate_and_invalid_registration(client, user, db):
    for data in [
        dict(username="COCINERO", password="secreto123", confirm="secreto123"),
        dict(username="a", password="123", confirm="no"),
        dict(username="user spaces", password="secreto123", confirm="secreto123"),
    ]:
        response = client.post("/register/", data=data)
        assert response.status_code == 200
    assert len(db.session.scalars(select(User)).all()) == 1


@pytest.mark.parametrize("password", ["incorrecta", ""])
def test_invalid_login(client, user, password):
    response = client.post(
        "/login/", data={"username": "cocinero", "password": password}
    )
    assert response.status_code == 200
    assert "/login/" in client.get("/cocina/").location


@pytest.mark.parametrize(
    "path",
    [
        "/cocina/",
        "/cocina/categorias/",
        "/cocina/ingredientes/",
        "/cocina/platos/",
        "/cocina/movimientos/",
        "/cocina/categorias/nueva/",
        "/cocina/movimientos/nuevo/",
    ],
)
def test_private_routes_redirect(client, path):
    assert "/login/" in client.get(path).location


@pytest.mark.parametrize(
    "target", ["https://evil.test", "//evil.test", "/\\evil.test", "//["]
)
def test_external_redirect_is_rejected(client, user, target):
    response = client.post(
        "/login/",
        query_string={"next": target},
        data={"username": user.username, "password": "secreto123"},
    )
    assert response.location == "/cocina/"


def test_safe_redirect(client, user):
    response = client.post(
        "/login/?next=/cocina/platos/",
        data={"username": user.username, "password": "secreto123"},
    )
    assert response.location == "/cocina/platos/"


def test_csrf_is_required_for_auth_and_inventory(client, app, user):
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        client.post(
            "/login/", data={"username": "cocinero", "password": "secreto123"}
        ).status_code
        == 400
    )
    csrf = token(client.get("/login/"))
    assert (
        client.post(
            "/login/",
            data={"username": "cocinero", "password": "secreto123", "csrf_token": csrf},
        ).status_code
        == 302
    )
    assert (
        client.post("/cocina/categorias/nueva/", data={"nombre": "Otra"}).status_code
        == 400
    )
    assert client.post("/logout/").status_code == 400
    assert client.get("/logout/").status_code == 405
    csrf = token(client.get("/cocina/"))
    assert client.post("/logout/", data={"csrf_token": csrf}).status_code == 302


def test_invalid_session_does_not_crash(client):
    with client.session_transaction() as session:
        session["_user_id"] = "not-a-number"
    assert client.get("/cocina/").status_code == 302
