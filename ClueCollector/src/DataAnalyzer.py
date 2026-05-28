"""Analysis helpers for raw ClueCollector observations.

DataCollector gathers low-level OS data. DataAnalyzer converts selected raw
results into compact summaries that are easier for the agent to reason about,
such as high-resource processes, risky external ports, and recent Defender
events.
"""

from typing import Dict, List
from statistics import mean
from datetime import datetime
from DataStructures import DefenderEventType, DefenderLog, ProcessSnapshot, PortInfo
from collections import defaultdict

class DataAnalyzer:
    """Summarizes raw collection data before it is returned to the agent."""

    def __init__(self, cpu_threshold=20, memory_threshold=20):
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold

    def analyze_processes(self, processes_data: List[ProcessSnapshot]) -> Dict:
        """
        Analyze process data and return summarized information about high-usage processes
        with time-series data averaged.
        """
        process_grouped = {}
        
        # Group process snapshots by PID-name combination
        for proc in processes_data:
            key = f"{proc.pid}-{proc.name}"
            if key not in process_grouped:
                process_grouped[key] = []
            process_grouped[key].append(proc)
        
        high_usage_processes = {
            'cpu': [],
            'memory': [],
            'both': []
        }
        
        last_timestamp = None
        
        for proc_key, proc_snapshots in process_grouped.items():
            first_snapshot = proc_snapshots[0]
            pid = first_snapshot.pid
            name = first_snapshot.name
            last_timestamp = proc_snapshots[-1].timestamp
            
            # Calculate averages using attribute access
            total_cpu_avg = round(mean([s.cpu_percent for s in proc_snapshots]), 1)
            estimated_cores = max([s.estimated_cores for s in proc_snapshots])
            cpu_per_core_avg = round(mean([s.cpu_per_core for s in proc_snapshots]), 1)
            memory_avg = round(mean([s.memory_percent for s in proc_snapshots]), 1)
            
            # Create process summary
            process_summary = {
                'pid': pid,
                'name': name,
                'memory_percent': memory_avg,
            }

            # Add CPU info based on number of cores
            if estimated_cores > 1:
                process_summary.update({
                    'cpu_total': total_cpu_avg,
                    'cpu_per_core': cpu_per_core_avg,
                    'estimated_cores': estimated_cores
                })
            else:
                process_summary['cpu_percent'] = cpu_per_core_avg
            
            # Categorize based on thresholds
            if cpu_per_core_avg >= self.cpu_threshold and memory_avg >= self.memory_threshold:
                high_usage_processes['both'].append(process_summary)
            elif cpu_per_core_avg >= self.cpu_threshold:
                high_usage_processes['cpu'].append(process_summary)
            elif memory_avg >= self.memory_threshold:
                high_usage_processes['memory'].append(process_summary)

        return high_usage_processes
    

    def analyze_open_ports(self, ports_data: List[PortInfo]) -> Dict:
        """
        Analyzes open ports data and identifies potentially risky connections.
        Filters out internal-only connections and categorizes remaining connections
        based on security risk level.
        """
        def is_internal_ip(ip: str) -> bool:
            # Localhost
            if ip in ('127.0.0.1', 'localhost') or ip.startswith('127.'):
                return True
                
            # Private IPv4 ranges
            ip_parts = ip.split('.')
            if len(ip_parts) != 4:
                return False
                
            try:
                first_octet = int(ip_parts[0])
                second_octet = int(ip_parts[1])
                
                return (
                    ip == '0.0.0.0' or  # Special case
                    first_octet == 10 or  # 10.0.0.0/8
                    (first_octet == 172 and 16 <= second_octet <= 31) or  # 172.16.0.0/12
                    (first_octet == 192 and second_octet == 168) or  # 192.168.0.0/16
                    (first_octet == 169 and second_octet == 254)  # 169.254.0.0/16 (link-local)
                )
            except ValueError:
                return False
        
        def is_internal_connection(port_info: PortInfo) -> bool:
            # Both endpoints are internal
            return (is_internal_ip(port_info.local_ip) and 
                    (port_info.remote_ip == '0.0.0.0' or is_internal_ip(port_info.remote_ip)))

        risky_ports = {
            'listening_external': [],  # Ports listening on external interfaces
            'established_external': [], # Active connections to external IPs
        }

        # Group connections by state and port
        listening_groups = defaultdict(lambda: {
            'protocol': None,
            'local_ip': set(),
            'local_port': set(),
            'remote_ip': set(),
            'remote_port': None,
            'state': None,
            'pid': set()
        })
        
        established_groups = defaultdict(lambda: {
            'protocol': None,
            'local_ip': None,
            'local_port': set(),
            'remote_ip': set(),
            'remote_port': None,
            'state': None,
            'pid': set()
        })
        
        for port_info in ports_data:
            if is_internal_connection(port_info):
                continue
                
            if port_info.state == 'LISTENING':
                if port_info.local_ip == '0.0.0.0':
                    group = listening_groups[port_info.local_port]
                    group['protocol'] = port_info.protocol
                    group['local_ip'].add(port_info.local_ip)
                    group['local_port'].add(port_info.local_port)
                    group['remote_ip'].add(port_info.remote_ip)
                    group['remote_port'] = port_info.remote_port
                    group['state'] = port_info.state
                    group['pid'].add(port_info.pid)
                    
            elif port_info.state == 'ESTABLISHED':
                if not is_internal_ip(port_info.remote_ip):
                    group = established_groups[port_info.remote_port]
                    group['protocol'] = port_info.protocol
                    group['local_ip'] = port_info.local_ip
                    group['local_port'].add(port_info.local_port)
                    group['remote_ip'].add(port_info.remote_ip)
                    group['remote_port'] = port_info.remote_port
                    group['state'] = port_info.state
                    group['pid'].add(port_info.pid)

        # Convert grouped data to final format
        for group in listening_groups.values():
            risky_ports['listening_external'].append({
                'protocol': group['protocol'],
                'local_ip': ', '.join(sorted(group['local_ip'])),
                'local_port': ', '.join(map(str, sorted(group['local_port']))),
                'remote_ip': ', '.join(sorted(group['remote_ip'])),
                'remote_port': group['remote_port'],
                'state': group['state'],
                'pid': ', '.join(map(str, sorted(group['pid'])))
            })
            
        for group in established_groups.values():
            risky_ports['established_external'].append({
                'protocol': group['protocol'],
                'local_ip': group['local_ip'],
                'local_port': ', '.join(map(str, sorted(group['local_port']))),
                'remote_ip': ', '.join(sorted(group['remote_ip'])),
                'remote_port': group['remote_port'],
                'state': group['state'],
                'pid': ', '.join(map(str, sorted(group['pid'])))
            })

        return risky_ports  
    

    # Define event ID mapping as a class variable
    DEFENDER_EVENT_MAPPING = {
        **{str(i): DefenderEventType.SERVICE_STATUS for i in range(1000, 1006)},
        **{str(i): DefenderEventType.DEFINITION_UPDATES for i in range(1006, 1010)},
        "1015": DefenderEventType.REALTIME_PROTECTION,
        **{str(i): DefenderEventType.MALWARE_DETECTED for i in range(1116, 1120)},
        "1121": DefenderEventType.MALWARE_BLOCKED,
        "1124": DefenderEventType.SUSPICIOUS_BEHAVIOR,
        "1125": DefenderEventType.SUSPICIOUS_BEHAVIOR,
        "1150": DefenderEventType.THREAT_REMEDIATED,
        "1151": DefenderEventType.THREAT_REMEDIATED,
        "5001": DefenderEventType.REALTIME_PROTECTION,
        "5004": DefenderEventType.SETTINGS_CHANGED,
        "5007": DefenderEventType.SETTINGS_CHANGED,
        "5008": DefenderEventType.ENGINE_UPDATES
    }

    def analyze_defender_logs(self, raw_logs: List[dict]) -> Dict[str, List[dict]]:
        """
        Analyze Windows Defender logs and organize them by type.
        Args:
            raw_logs: List of raw log entries from Get-WinEvent
        Returns:
            Dict: Organized logs by event type
        """
        # Initialize empty lists for each event type using enum values
        logs_by_type = {}
        for event_type in DefenderEventType:
            logs_by_type[event_type.value] = []  

        # Keep track of latest log for each event ID
        latest_logs = {}
        
        for log in raw_logs:
            event_id = str(log['Id'])
            
            if event_id not in self.DEFENDER_EVENT_MAPPING:
                continue
                
            # Check if this is the latest entry for this event ID
            if event_id not in latest_logs or \
               datetime.strptime(log['TimeCreated'], '%Y-%m-%d %H:%M:%S') > \
               datetime.strptime(latest_logs[event_id]['TimeCreated'], '%Y-%m-%d %H:%M:%S'):
                latest_logs[event_id] = log

        # Create DefenderLog objects from the latest logs
        for event_id, log in latest_logs.items():
            event_type = self.DEFENDER_EVENT_MAPPING[event_id]
            defender_log = DefenderLog(
                event_type=event_type,
                time_generated=log['TimeCreated'],
                message=log['Message'],
                event_id=event_id
            )
            logs_by_type[event_type.value].append(defender_log.to_dict())

        # Sort logs within each type by event ID
        for event_type in logs_by_type:
            logs_by_type[event_type].sort(key=lambda x: int(x['event_id']))

        return logs_by_type
