import uuid


async def _login_as_admin(client, seed_user, username: str = "admin") -> None:
    _, password = await seed_user(username=username)
    response = await client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200


async def _create_team(client, name: str = "North Zone") -> str:
    response = await client.post("/teams", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_directory_user(client, mobile: str, team_id: str, name: str = "Karim") -> str:
    response = await client.post(
        "/users", json={"name": name, "mobile": mobile, "role": "sales_user", "team_id": team_id}
    )
    assert response.status_code == 201
    return response.json()["id"]


# --- Auth enforcement (AD-8) --------------------------------------------------


async def test_list_users_without_cookie_returns_401(client):
    response = await client.get("/users")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_list_teams_without_cookie_returns_401(client):
    response = await client.get("/teams")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_list_recipient_lists_without_cookie_returns_401(client):
    response = await client.get("/recipient-lists")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_grant_opt_in_consent_without_cookie_returns_401(client):
    response = await client.post(f"/users/{uuid.uuid4()}/opt-in-consent")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_revoke_opt_in_consent_without_cookie_returns_401(client):
    response = await client.delete(f"/users/{uuid.uuid4()}/opt-in-consent")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- POST /users ---------------------------------------------------------------


async def test_create_user_succeeds_and_is_audit_logged(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)

    response = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000201",
            "role": "sales_user",
            "team_id": team_id,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Karim"
    assert body["mobile"] == "+8801700000201"
    assert body["role"] == "sales_user"
    assert body["status"] == "active"
    assert body["team_id"] == team_id
    assert body["team_name"] == "North Zone"
    assert body["username"] is None


async def test_create_user_with_administrator_role_is_rejected_by_request_validation(
    client, seed_user
):
    """The Literal["sales_user","manager"] type on the request body is the
    first line of defense (AC #5) — "administrator" fails standard Pydantic
    validation before the route body, let alone the domain layer, ever runs."""
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)

    response = await client.post(
        "/users",
        json={
            "name": "Someone",
            "mobile": "+8801700000202",
            "role": "administrator",
            "team_id": team_id,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_create_user_with_a_taken_mobile_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000203",
            "role": "sales_user",
            "team_id": team_id,
        },
    )

    response = await client.post(
        "/users",
        json={"name": "Other", "mobile": "+8801700000203", "role": "manager", "team_id": team_id},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "mobile_taken"


async def test_create_user_with_a_nonexistent_team_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000214",
            "role": "sales_user",
            "team_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_user_with_an_inactive_team_returns_422(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    await client.delete(f"/teams/{team_id}")

    response = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000215",
            "role": "sales_user",
            "team_id": team_id,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "team_inactive"


async def test_removed_users_mobile_becomes_available_for_a_new_user(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000216",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]
    await client.delete(f"/users/{user_id}")

    response = await client.post(
        "/users",
        json={
            "name": "Replacement",
            "mobile": "+8801700000216",
            "role": "sales_user",
            "team_id": team_id,
        },
    )

    assert response.status_code == 201
    assert response.json()["mobile"] == "+8801700000216"


# --- GET /users ------------------------------------------------------------------


async def test_list_users_includes_administrators_and_sales_users(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000204",
            "role": "sales_user",
            "team_id": team_id,
        },
    )

    response = await client.get("/users")

    assert response.status_code == 200
    roles = {row["role"] for row in response.json()}
    assert "administrator" in roles
    assert "sales_user" in roles


async def test_list_users_reports_per_user_consent_status_in_the_same_call(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    opted_in_id = await _create_directory_user(client, "+8801700000217", team_id, "Opted In")
    never_opted_id = await _create_directory_user(client, "+8801700000218", team_id, "Never Opted")
    await client.post(f"/users/{opted_in_id}/opt-in-consent")

    response = await client.get("/users")

    assert response.status_code == 200
    by_id = {row["id"]: row for row in response.json()}
    assert by_id[opted_in_id]["consent_status"] == "opted_in"
    assert by_id[opted_in_id]["consent_recorded_at"] is not None
    assert by_id[never_opted_id]["consent_status"] == "not_opted_in"
    assert by_id[never_opted_id]["consent_recorded_at"] is None


# --- GET /users/mobile-availability -----------------------------------------------


async def test_mobile_availability_is_true_for_an_unused_mobile(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.get("/users/mobile-availability", params={"mobile": "+8801700000205"})

    assert response.status_code == 200
    assert response.json() == {"available": True}


async def test_mobile_availability_is_false_for_a_taken_mobile(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000206",
            "role": "sales_user",
            "team_id": team_id,
        },
    )

    response = await client.get("/users/mobile-availability", params={"mobile": "+8801700000206"})

    assert response.json() == {"available": False}


async def test_mobile_availability_excludes_the_user_being_edited(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000207",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]

    response = await client.get(
        "/users/mobile-availability",
        params={"mobile": "+8801700000207", "exclude_user_id": user_id},
    )

    assert response.json() == {"available": True}


# --- PATCH /users/{id} ----------------------------------------------------------


async def test_update_user_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    other_team_id = await _create_team(client, "South Zone")
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000208",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]

    response = await client.patch(
        f"/users/{user_id}",
        json={
            "name": "Karim Updated",
            "mobile": "+8801700000209",
            "team_id": other_team_id,
            "version": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Karim Updated"
    assert body["mobile"] == "+8801700000209"
    assert body["team_id"] == other_team_id


async def test_update_user_changing_mobile_on_an_opted_in_user_returns_not_opted_in(
    client, seed_user
):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000219",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]
    await client.post(f"/users/{user_id}/opt-in-consent")

    response = await client.patch(
        f"/users/{user_id}",
        json={"name": "Karim", "mobile": "+8801700000220", "team_id": team_id, "version": 1},
    )

    assert response.status_code == 200
    assert response.json()["consent_status"] == "not_opted_in"


async def test_update_user_with_a_mobile_taken_by_another_user_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    await client.post(
        "/users",
        json={"name": "A", "mobile": "+8801700000210", "role": "sales_user", "team_id": team_id},
    )
    created = await client.post(
        "/users",
        json={"name": "B", "mobile": "+8801700000211", "role": "sales_user", "team_id": team_id},
    )
    user_id = created.json()["id"]

    response = await client.patch(
        f"/users/{user_id}",
        json={"name": "B", "mobile": "+8801700000210", "team_id": team_id, "version": 1},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "mobile_taken"


async def test_update_user_with_a_stale_version_returns_409_version_conflict(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000221",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]
    await client.patch(
        f"/users/{user_id}",
        json={
            "name": "Karim First Update",
            "mobile": "+8801700000221",
            "team_id": team_id,
            "version": 1,
        },
    )

    response = await client.patch(
        f"/users/{user_id}",
        json={
            "name": "Karim Stale Update",
            "mobile": "+8801700000221",
            "team_id": team_id,
            "version": 1,
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "version_conflict"
    assert body["error"]["details"]["current"]["version"] == 2
    assert body["error"]["details"]["current"]["name"] == "Karim First Update"


async def test_update_user_with_version_omitted_returns_422(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000222",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]

    response = await client.patch(
        f"/users/{user_id}",
        json={"name": "Karim", "mobile": "+8801700000222", "team_id": team_id},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_update_user_on_an_administrator_returns_400(client, seed_user):
    admin, _ = await seed_user(username="admin")
    await _login_as_admin(client, seed_user, username="admin2")
    team_id = await _create_team(client)

    response = await client.patch(
        f"/users/{admin.id}",
        json={"name": "New Name", "mobile": "+8801700000212", "team_id": team_id, "version": 1},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "administrator_not_editable"


# --- DELETE /users/{id} ---------------------------------------------------------


async def test_remove_user_deactivates_a_sales_user(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    created = await client.post(
        "/users",
        json={
            "name": "Karim",
            "mobile": "+8801700000213",
            "role": "sales_user",
            "team_id": team_id,
        },
    )
    user_id = created.json()["id"]

    response = await client.delete(f"/users/{user_id}")

    assert response.status_code == 204
    listed = await client.get("/users")
    row = next(row for row in listed.json() if row["id"] == user_id)
    assert row["status"] == "inactive"


async def test_remove_the_sole_active_administrator_returns_409(client, seed_user):
    admin, password = await seed_user(username="admin")
    login = await client.post("/auth/login", json={"username": "admin", "password": password})
    assert login.status_code == 200

    response = await client.delete(f"/users/{admin.id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_administrator"


# --- POST /teams -----------------------------------------------------------------


async def test_create_team_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post("/teams", json={"name": "East Zone"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "East Zone"
    assert body["status"] == "active"
    assert body["version"] == 1


async def test_create_team_with_a_taken_name_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    await client.post("/teams", json={"name": "East Zone"})

    response = await client.post("/teams", json={"name": "East Zone"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "team_name_taken"


# --- GET /teams --------------------------------------------------------------------


async def test_list_teams_returns_created_teams(client, seed_user):
    await _login_as_admin(client, seed_user)
    await client.post("/teams", json={"name": "East Zone"})

    response = await client.get("/teams")

    assert response.status_code == 200
    names = {row["name"] for row in response.json()}
    assert "East Zone" in names


# --- PATCH /teams/{id} -------------------------------------------------------------


async def test_update_team_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client, "East Zone")

    response = await client.patch(f"/teams/{team_id}", json={"name": "Eastern Zone", "version": 1})

    assert response.status_code == 200
    assert response.json()["name"] == "Eastern Zone"


async def test_update_team_to_a_taken_name_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    await _create_team(client, "East Zone")
    team_id = await _create_team(client, "West Zone")

    response = await client.patch(f"/teams/{team_id}", json={"name": "East Zone", "version": 1})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "team_name_taken"


async def test_update_team_with_a_stale_version_returns_409_version_conflict(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client, "East Zone")
    await client.patch(f"/teams/{team_id}", json={"name": "Eastern Zone", "version": 1})

    response = await client.patch(f"/teams/{team_id}", json={"name": "Stale Zone", "version": 1})

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "version_conflict"
    assert body["error"]["details"]["current"]["version"] == 2
    assert body["error"]["details"]["current"]["name"] == "Eastern Zone"


async def test_update_team_with_version_omitted_returns_422(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client, "East Zone")

    response = await client.patch(f"/teams/{team_id}", json={"name": "Eastern Zone"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- DELETE /teams/{id} -------------------------------------------------------------


async def test_removed_teams_name_becomes_available_for_a_new_team(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client, "East Zone")
    await client.delete(f"/teams/{team_id}")

    response = await client.post("/teams", json={"name": "East Zone"})

    assert response.status_code == 201


async def test_remove_team_deactivates_it(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client, "East Zone")

    response = await client.delete(f"/teams/{team_id}")

    assert response.status_code == 204
    listed = await client.get("/teams")
    row = next(row for row in listed.json() if row["id"] == team_id)
    assert row["status"] == "inactive"


# --- POST /recipient-lists -------------------------------------------------------


async def test_create_recipient_list_group_succeeds_and_is_audit_logged(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    member_id = await _create_directory_user(client, "+8801700000501", team_id)

    response = await client.post(
        "/recipient-lists",
        json={"name": "North Group", "kind": "group", "member_user_ids": [member_id]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "North Group"
    assert body["kind"] == "group"
    assert body["status"] == "active"
    assert body["version"] == 1
    assert body["member_user_ids"] == [member_id]


async def test_create_recipient_list_channel_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post(
        "/recipient-lists", json={"name": "North Channel", "kind": "channel", "member_user_ids": []}
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "channel"


async def test_create_recipient_list_with_a_taken_name_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )

    response = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "channel", "member_user_ids": []}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "recipient_list_name_taken"


async def test_create_recipient_list_with_a_nonexistent_member_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post(
        "/recipient-lists",
        json={"name": "North Group", "kind": "group", "member_user_ids": [str(uuid.uuid4())]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_recipient_list_with_an_inactive_member_returns_422(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    member_id = await _create_directory_user(client, "+8801700000502", team_id)
    await client.delete(f"/users/{member_id}")

    response = await client.post(
        "/recipient-lists",
        json={"name": "North Group", "kind": "group", "member_user_ids": [member_id]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "member_inactive"


async def test_create_recipient_list_with_an_administrator_member_returns_422(client, seed_user):
    admin, _ = await seed_user(username="admin")
    await _login_as_admin(client, seed_user, username="admin2")

    response = await client.post(
        "/recipient-lists",
        json={"name": "North Group", "kind": "group", "member_user_ids": [str(admin.id)]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "member_not_addressable"


# --- GET /recipient-lists ---------------------------------------------------------


async def test_list_recipient_lists_includes_groups_and_channels(client, seed_user):
    await _login_as_admin(client, seed_user)
    await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    await client.post(
        "/recipient-lists", json={"name": "North Channel", "kind": "channel", "member_user_ids": []}
    )

    response = await client.get("/recipient-lists")

    assert response.status_code == 200
    kinds = {row["kind"] for row in response.json()}
    assert kinds == {"group", "channel"}


# --- PATCH /recipient-lists/{id} --------------------------------------------------


async def test_update_recipient_list_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    member_id = await _create_directory_user(client, "+8801700000503", team_id)
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]

    response = await client.patch(
        f"/recipient-lists/{recipient_list_id}",
        json={
            "name": "North Channel",
            "kind": "channel",
            "member_user_ids": [member_id],
            "version": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "North Channel"
    assert body["kind"] == "channel"
    assert body["member_user_ids"] == [member_id]


async def test_update_recipient_list_on_an_unknown_id_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.patch(
        f"/recipient-lists/{uuid.uuid4()}",
        json={"name": "Name", "kind": "group", "member_user_ids": [], "version": 1},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_update_recipient_list_to_a_name_taken_by_another_list_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    await client.post(
        "/recipient-lists", json={"name": "South Group", "kind": "group", "member_user_ids": []}
    )
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]

    response = await client.patch(
        f"/recipient-lists/{recipient_list_id}",
        json={"name": "South Group", "kind": "group", "member_user_ids": [], "version": 1},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "recipient_list_name_taken"


async def test_update_recipient_list_with_an_administrator_member_returns_422(client, seed_user):
    admin, _ = await seed_user(username="admin")
    await _login_as_admin(client, seed_user, username="admin2")
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]

    response = await client.patch(
        f"/recipient-lists/{recipient_list_id}",
        json={
            "name": "North Group",
            "kind": "group",
            "member_user_ids": [str(admin.id)],
            "version": 1,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "member_not_addressable"


async def test_update_recipient_list_with_a_stale_version_returns_409_version_conflict(
    client, seed_user
):
    await _login_as_admin(client, seed_user)
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]
    await client.patch(
        f"/recipient-lists/{recipient_list_id}",
        json={"name": "North Channel", "kind": "channel", "member_user_ids": [], "version": 1},
    )

    response = await client.patch(
        f"/recipient-lists/{recipient_list_id}",
        json={"name": "Stale Name", "kind": "group", "member_user_ids": [], "version": 1},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "version_conflict"
    assert body["error"]["details"]["current"]["version"] == 2
    assert body["error"]["details"]["current"]["name"] == "North Channel"
    assert body["error"]["details"]["current"]["kind"] == "channel"


async def test_update_recipient_list_with_version_omitted_returns_422(client, seed_user):
    await _login_as_admin(client, seed_user)
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]

    response = await client.patch(
        f"/recipient-lists/{recipient_list_id}",
        json={"name": "North Group", "kind": "group", "member_user_ids": []},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- DELETE /recipient-lists/{id} -------------------------------------------------


async def test_remove_recipient_list_deactivates_it(client, seed_user):
    await _login_as_admin(client, seed_user)
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]

    response = await client.delete(f"/recipient-lists/{recipient_list_id}")

    assert response.status_code == 204
    listed = await client.get("/recipient-lists")
    row = next(row for row in listed.json() if row["id"] == recipient_list_id)
    assert row["status"] == "inactive"


async def test_remove_recipient_list_on_an_unknown_id_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.delete(f"/recipient-lists/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_removed_recipient_lists_name_becomes_available_for_a_new_list(client, seed_user):
    await _login_as_admin(client, seed_user)
    created = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "group", "member_user_ids": []}
    )
    recipient_list_id = created.json()["id"]
    await client.delete(f"/recipient-lists/{recipient_list_id}")

    response = await client.post(
        "/recipient-lists", json={"name": "North Group", "kind": "channel", "member_user_ids": []}
    )

    assert response.status_code == 201


# --- POST /users/{id}/opt-in-consent ----------------------------------------


async def test_grant_opt_in_consent_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_directory_user(client, "+8801700000601", team_id)

    response = await client.post(f"/users/{user_id}/opt-in-consent")

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user_id
    assert "granted_at" in body


async def test_grant_opt_in_consent_for_a_nonexistent_user_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.post(f"/users/{uuid.uuid4()}/opt-in-consent")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_grant_opt_in_consent_for_an_administrator_returns_422(client, seed_user):
    admin, _ = await seed_user(username="admin")
    await _login_as_admin(client, seed_user, username="admin2")

    response = await client.post(f"/users/{admin.id}/opt-in-consent")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "consent_not_addressable"


async def test_grant_opt_in_consent_a_second_time_without_revoking_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_directory_user(client, "+8801700000602", team_id)
    await client.post(f"/users/{user_id}/opt-in-consent")

    response = await client.post(f"/users/{user_id}/opt-in-consent")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_already_active"


# --- DELETE /users/{id}/opt-in-consent --------------------------------------


async def test_revoke_opt_in_consent_succeeds(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_directory_user(client, "+8801700000603", team_id)
    await client.post(f"/users/{user_id}/opt-in-consent")

    response = await client.delete(f"/users/{user_id}/opt-in-consent")

    assert response.status_code == 204


async def test_revoke_opt_in_consent_when_nothing_active_returns_409(client, seed_user):
    await _login_as_admin(client, seed_user)
    team_id = await _create_team(client)
    user_id = await _create_directory_user(client, "+8801700000604", team_id)

    response = await client.delete(f"/users/{user_id}/opt-in-consent")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_not_active"


async def test_revoke_opt_in_consent_for_a_nonexistent_user_returns_404(client, seed_user):
    await _login_as_admin(client, seed_user)

    response = await client.delete(f"/users/{uuid.uuid4()}/opt-in-consent")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
