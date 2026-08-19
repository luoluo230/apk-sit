# -*- coding: utf-8 -*-
"""Backward-compatible facade over room_service."""

from __future__ import annotations

from services.baas import room_service

matchmake = room_service.matchmake
get_room = room_service.get_room
sync_state = room_service.sync_state
leave_room = room_service.leave_room
poll_frames = room_service.poll_frames
get_frames = room_service.get_frames
