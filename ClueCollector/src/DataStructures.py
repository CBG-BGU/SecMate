"""Typed records used by ClueCollector collection and analysis code."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


@dataclass
class ProcessSnapshot:
    """One sampled observation of a running process."""

    timestamp: str
    pid: int
    name: str
    cpu_percent: float
    estimated_cores: int
    cpu_per_core: float
    memory_percent: float

    def to_dict(self) -> Dict:
        """Convert ProcessSnapshot to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp,
            "pid": self.pid,
            "name": self.name,
            "cpu_percent": self.cpu_percent,
            "estimated_cores": self.estimated_cores,
            "cpu_per_core": self.cpu_per_core,
            "memory_percent": self.memory_percent
        }
        
    
class SecurityLevel(Enum):
    """Simple ordering for Wi-Fi security strength."""

    NONE = 0
    WEP = 1
    WPA = 2
    WPA2 = 3
    WPA3 = 4

@dataclass
class NetworkInfo:
    """A Wi-Fi network observed during a scan."""

    ssid: str
    security_level: SecurityLevel
    signal_strength: int  # in dBm
    requires_password: bool
    is_connected: bool = False

    def to_dict(self) -> Dict:
        """Convert NetworkInfo to dictionary for JSON serialization"""
        return {
            "ssid": self.ssid,
            "security_level": self.security_level.name,
            "signal_strength": self.signal_strength,
            "requires_password": self.requires_password,
            "is_connected": self.is_connected
        }
    

@dataclass
class PortInfo:
    """A listening or established network connection."""

    protocol: str
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    state: str
    pid: int

    def to_dict(self) -> Dict:
        return {
            "protocol": self.protocol,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "remote_ip": self.remote_ip,
            "remote_port": self.remote_port,
            "state": self.state,
            "pid": self.pid
        }
    

class DefenderEventType(Enum):
    """Windows Defender event categories used by the analyzer."""

    SERVICE_STATUS = "service_status"              # 1000-1005
    DEFINITION_UPDATES = "definition_updates"      # 1006-1009
    REALTIME_PROTECTION = "realtime_protection"    # 1015, 5001
    MALWARE_DETECTED = "malware_detected"          # 1116-1119
    MALWARE_BLOCKED = "malware_blocked"            # 1121
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior"    # 1124-1125
    THREAT_REMEDIATED = "threat_remediated"        # 1150-1151
    SETTINGS_CHANGED = "settings_changed"          # 5004, 5007
    ENGINE_UPDATES = "engine_updates"              # 5008

@dataclass
class DefenderLog:
    """Normalized Defender log entry returned to the agent."""

    event_type: DefenderEventType
    time_generated: str
    message: str
    event_id: str

    def _format_message(self, message: str) -> str:
        """Format message by properly handling newlines and indentation."""
        # Split message into lines
        lines = message.split('\\r\\n')
        # Remove empty lines and strip whitespace
        lines = [line.strip() for line in lines if line.strip()]
        # Remove \t and extra spaces
        lines = [line.replace('\\t', '').strip() for line in lines]
        # Join with newlines
        return '\n'.join(lines)
    
    def to_dict(self) -> Dict:
        return {
            "time_generated": self.time_generated,
            "event_id": self.event_id,
            "message": self._format_message(self.message)
        }
