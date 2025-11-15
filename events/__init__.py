"""
Events Module - Phase 2 Implementation

This module provides event classes for simulating environmental conditions
and potential attacks on the satellite system.

Components:
- base: Event base class and type definitions
- environmental: Natural space environment events
- attacks: Simulated attack scenarios
- manager: Event generation and management
"""

from events.base import Event, EventType, EventSeverity

__all__ = ['Event', 'EventType', 'EventSeverity']
