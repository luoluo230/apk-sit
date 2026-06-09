# -*- coding: utf-8 -*-
"""Shared stdlib imports for ops route modules."""
from __future__ import annotations

import hashlib
import json
import os
import queue as _queue_mod
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from config import DATA_DIR
import services.ops.constants as _ops_constants

for _k, _v in vars(_ops_constants).items():
    if not _k.startswith("__"):
        globals()[_k] = _v
del _k, _v, _ops_constants
