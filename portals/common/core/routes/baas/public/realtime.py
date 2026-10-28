# -*- coding: utf-8 -*-
"""BaaS public routes: realtime."""

from routes.baas.public._deps import *  # noqa: F401,F403


def register(target):
    prefix = "/api/baas/v1/<service_id>"

    @target.route(f"{prefix}/rooms", methods=["GET", "POST"])
    def baas_rooms(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        if request.method == "GET":
            env_key = str(request.args.get("env_key") or "")
            try:
                return jsonify({"ok": True, "data": room_service.list_public_rooms(service_id, env_key=env_key)})
            except ValueError as exc:
                return baas_fail_exc(exc)
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    "data": room_service.create_room(
                        service_id,
                        player["player_id"],
                        visibility=str(body.get("visibility") or "public"),
                        max_players=body.get("max_players"),
                        env_key=str(body.get("env_key") or ""),
                        battle_mode=str(body.get("battle_mode") or "pvp_1v1"),
                        password=str(body.get("password") or ""),
                    ),
                }
            )
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/join", methods=["POST"])
    def baas_room_join(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    "data": room_service.join_room(
                        service_id,
                        player["player_id"],
                        room_id=str(body.get("room_id") or ""),
                        invite_code=str(body.get("invite_code") or ""),
                        password=str(body.get("password") or ""),
                        as_spectator=bool(body.get("as_spectator")),
                    ),
                }
            )
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/rejoin", methods=["POST"])
    def baas_room_rejoin(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": room_service.rejoin_room(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/disconnect", methods=["POST"])
    def baas_room_disconnect(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": room_service.mark_disconnected(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/kick", methods=["POST"])
    def baas_room_kick(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        target_id = str(body.get("target_id") or "").strip()
        try:
            return jsonify({"ok": True, "data": room_service.kick_player(service_id, room_id, player["player_id"], target_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/start-battle", methods=["POST"])
    def baas_room_start_battle(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": room_service.start_battle(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/frames", methods=["GET", "POST"])
    def baas_room_frames(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        if request.method == "GET":
            since_seq = int(request.args.get("since_seq") or 0)
            wait_ms = int(request.args.get("wait_ms") or 0)
            exclude_player = str(request.headers.get("X-Baas-Player-Id") or request.args.get("exclude_player_id") or "").strip()
            try:
                if wait_ms > 0:
                    data = room_service.poll_frames(
                        service_id,
                        room_id,
                        since_seq=since_seq,
                        wait_ms=wait_ms,
                        exclude_player_id=exclude_player,
                    )
                else:
                    data = room_service.get_frames(service_id, room_id, since_seq=since_seq)
                return jsonify({"ok": True, "data": data})
            except ValueError as exc:
                return baas_fail_exc(exc)
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": room_service.push_frame(service_id, room_id, player["player_id"], body.get("frame") or {})})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/rooms/<room_id>/finish-battle", methods=["POST"])
    def baas_room_finish_battle(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": room_service.finish_battle(service_id, room_id, player["player_id"], body.get("result") or {})})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/replays/<replay_id>", methods=["GET"])
    def baas_replay_get(service_id: str, replay_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            return jsonify({"ok": True, "data": room_service.get_replay(service_id, replay_id)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/matchmake", methods=["POST"])
    def baas_pvp_match(service_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(
                {
                    "ok": True,
                    "data": pvp_service.matchmake(
                        service_id,
                        player["player_id"],
                        env_key=str(body.get("env_key") or ""),
                        battle_mode=str(body.get("battle_mode") or ""),
                    ),
                }
            )
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/rooms/<room_id>", methods=["GET"])
    def baas_pvp_room(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        try:
            viewer = str(request.headers.get("X-Baas-Player-Id") or request.args.get("player_id") or "").strip()
            return jsonify({"ok": True, "data": pvp_service.get_room(service_id, room_id, viewer_id=viewer)})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/rooms/<room_id>/state", methods=["POST"])
    def baas_pvp_sync(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        body = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, "data": pvp_service.sync_state(service_id, room_id, player["player_id"], body.get("state") or {})})
        except ValueError as exc:
            return baas_fail_exc(exc)

    @target.route(f"{prefix}/pvp/rooms/<room_id>/leave", methods=["POST"])
    def baas_pvp_leave(service_id: str, room_id: str):
        sid, err = _service_auth(service_id)
        if err:
            return err
        player, perr = _player_auth(service_id)
        if perr:
            return perr
        try:
            return jsonify({"ok": True, "data": pvp_service.leave_room(service_id, room_id, player["player_id"])})
        except ValueError as exc:
            return baas_fail_exc(exc)


