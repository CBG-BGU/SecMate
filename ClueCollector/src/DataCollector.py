"""System information collection routines used by ClueCollector.

The SecMate Orchestrator can request one of the endpoint names defined in ``Actions``.
ClueCollector keeps recent results in memory, refreshes dynamic endpoints in a
background scheduler, and returns the latest result to the WebSocket bridge when
the server asks for it.
"""

import re
from concurrent.futures import ThreadPoolExecutor
import pythoncom
import platform
import psutil
import GPUtil
import subprocess
from typing import List
import queue
import threading
import logging
import time
import sys
import json
import os 
import winreg
import wmi
from datetime import datetime, timedelta
import pywifi
from pywifi import const
from enum import Enum
from math import ceil
from DataAnalyzer import DataAnalyzer  
from DataStructures import ProcessSnapshot, SecurityLevel, NetworkInfo, PortInfo


class Actions(Enum):
    """Actions exposed to the Orchestrator through the ClueCollector bridge."""

    GET_CPU_INFO = "get_cpu_info"
    GET_OS_INFO = "get_os_info"
    GET_RAM_INFO = "get_ram_info"
    GET_GPU_INFO = "get_gpu_info"
    GET_STORAGE_INFO = "get_storage_info"
    GET_PERIPHERALS_INFO = "get_peripherals_info"
    GET_INSTALLED_SOFTWARE_INFO = "get_installed_software_info"
    GET_BROWSER_EXTENSIONS = "get_browser_extensions"
    GET_FIREWALL_STATUS = "get_firewall_status"
    GET_DEFENDER_STATUS = "get_defender_status"
    GET_OPEN_PORTS = "get_open_ports"
    GET_RUNNING_PROCESSES = "get_running_processes"
    GET_INSTALLED_SOFTWARE_RECENTLY = "get_installed_software_recently"
    GET_RECENT_DOWNLOADS = "get_recent_downloads"
    GET_NETWORK_INFO = "get_network_info"


class DataCollector:
    """Collects system data and stores the latest result for each action."""

    def __init__(self):
        self.results_dict = {}
        self.task_queue = queue.PriorityQueue()
        self.results_lock = threading.Lock()
        self.should_run = threading.Event()
        self.should_run.set()
        self.worker_thread = threading.Thread(target=self.task_worker, daemon=True)
        self.worker_thread.start()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.current_tasks = set()
        self.current_tasks_lock = threading.Lock()
        self.task_counter = 0

        self.refresh_interval = 5  # Interval in seconds
        self.actions_to_refresh = [
            Actions.GET_RAM_INFO,
            Actions.GET_FIREWALL_STATUS,
            Actions.GET_DEFENDER_STATUS,
            Actions.GET_RUNNING_PROCESSES,
            Actions.GET_INSTALLED_SOFTWARE_RECENTLY,
            Actions.GET_RECENT_DOWNLOADS,
        ]
        self.scheduler_thread = threading.Thread(target=self._scheduler_worker, daemon=True)
        self.scheduler_thread.start()

    def _scheduler_worker(self):
        """Periodically re-queue dynamic actions so cached data stays fresh."""
        logging.info(f"Scheduler started. Refreshing tasks every {self.refresh_interval} seconds.")
        
        while self.should_run.is_set():
            for _ in range(self.refresh_interval):
                if not self.should_run.is_set():
                    logging.info("Scheduler worker stopping during wait.")
                    return
                time.sleep(1)

            if self.should_run.is_set():
                logging.info("Scheduler: Re-queuing tasks for periodic refresh.")
                for action in self.actions_to_refresh:
                    self.queue_action(action, priority=20)
                    
        logging.info("Scheduler worker has stopped.")
                
    def task_worker(self):
        """
        Run collector actions from the priority queue.

        The worker keeps slow OS calls off the WebSocket thread. Results are
        cached by action, and the bridge returns the most recent cached value.
        """
        while self.should_run.is_set():
            try:
                priority, count, action = self.task_queue.get(block=True, timeout=1)
                
                logging.info(f"Submitting task: {action.value} with priority {priority}")
                
                try:
                    future = self.executor.submit(getattr(self, action.value))
                    result = future.result()
                    
                    with self.results_lock:
                        self.results_dict[action] = result
                    
                    execution_time = result.get('execution_time', 0) if isinstance(result, dict) else 0
                    output_size = len(json.dumps(result)) if result else 0
                    logging.info(
                        f"Task {action.value} completed. Execution time: {execution_time:.2f}s. Output size: {output_size} chars."
                    )

                except Exception as e:
                    logging.error(f"Task {action.value} failed with error: {e}", exc_info=True)
                finally:
                    self.task_queue.task_done()

            except queue.Empty:
                continue

    def queue_action(self, action: Actions, priority=10):
        """Queue an action for collection."""
        self.task_counter += 1
        self.task_queue.put((priority, self.task_counter, action))

    def get_result(self, action: Actions):
        """Return the most recent cached result for an action."""
        with self.results_lock:
            return self.results_dict.get(action)

    def start_initial_data_collection(self):
        """Queue all supported actions once when ClueCollector starts."""
        for action in Actions:
            self.queue_action(action, priority=10)
        logging.info("Initial data collection tasks queued.")

    def stop(self):
        """Stop scheduler, worker thread, and executor resources."""
        logging.info(f"{self.__class__.__name__} is being stopped...")
        self.should_run.clear()

        self.worker_thread.join()
        self.scheduler_thread.join() 

        self.executor.shutdown(wait=True, cancel_futures=True)

        logging.info(f"{self.__class__.__name__} stopped.")

    @staticmethod
    def get_os_info():
        """Return basic operating system name and version."""
        os_name = platform.system()
        os_version = platform.release()
        logging.info('OS information fetched')
        return {"os_name": os_name, "os_version": os_version}


    @staticmethod
    def get_open_ports():
        """Return listening and established external network connections."""
        command = ["netstat", "-ano"] 
        result = DataCollector._safe_command_execution(command)
        output = result.stdout

        pattern = re.compile(r'^\s*(TCP|UDP)\s+([\d\.\:]+)\s+([\d\.\:]+)\s+(\S+)\s+(\d+)$', re.MULTILINE)

        ports_data = []
        for match in pattern.finditer(output):
            protocol = match.group(1)
            local_address = match.group(2)
            remote_address = match.group(3)
            state = match.group(4)
            pid = match.group(5)

            local_ip, local_port = local_address.rsplit(':', 1)
            remote_ip, remote_port = remote_address.rsplit(':', 1)

            if state in ("LISTENING", "ESTABLISHED"):
                port_info = PortInfo(
                protocol=protocol,
                local_ip=local_ip,
                local_port=int(local_port),
                remote_ip=remote_ip,
                remote_port=int(remote_port),
                state=state,
                pid=int(pid)
                )
                ports_data.append(port_info)

        # Analyze the collected data
        analyzer = DataAnalyzer()
        analysis_results = analyzer.analyze_open_ports(ports_data)
                
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "open_ports": analysis_results
        }


    @staticmethod
    def get_running_processes():
        """
        Return process resource usage and a compact high-usage analysis.
        """
        try:
            start_time = time.time()
            logging.info("Starting process collection...")
            
            # Initialize empty list for snapshots
            processes_data = []
            simple_processes = []
            cpu_count = psutil.cpu_count(logical=True)
            
            def estimate_cores_used(cpu_percent: float) -> int:
                """Estimate number of cores used based on CPU percentage"""
                estimated_cores = ceil(cpu_percent / 100)
                return min(estimated_cores, cpu_count)
            
            # Initialize CPU monitoring with error handling
            for proc in psutil.process_iter():
                try:
                    proc.cpu_percent()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            time.sleep(0.5)
            
            # Keep original duration but make it configurable
            duration = 5
            interval = 0.5
            
            logging.info(f"Collecting process data for {duration} seconds...")
            
            end_time = time.time() + duration
            snapshot_count = 0
            
            while time.time() < end_time:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                snapshot_count += 1

                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                    try:
                        info = proc.info
                        if info['pid'] == 0:
                            continue

                        cpu_percent = info['cpu_percent']
                        estimated_cores = estimate_cores_used(cpu_percent)
                        cpu_per_core = round(cpu_percent / estimated_cores, 1) if estimated_cores > 0 else 0

                        snapshot = ProcessSnapshot(
                            timestamp=timestamp,
                            pid=info['pid'],
                            name=info['name'],
                            cpu_percent=cpu_percent,
                            estimated_cores=estimated_cores,
                            cpu_per_core=cpu_per_core,
                            memory_percent=info['memory_percent']
                        )
                        processes_data.append(snapshot)
                        
                        if snapshot_count == 1:
                            simple_processes.append({
                                'pid': info['pid'],
                                'name': info['name'],
                                'cpu_percent': round(cpu_percent, 2),
                                'memory_percent': round(info['memory_percent'], 2)
                            })

                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as e:
                        logging.debug(f"Could not access process information: {str(e)}")
                        continue
                
                time.sleep(interval)

            logging.info(f"Collected {snapshot_count} snapshots with {len(processes_data)} total process records")

            analyzer = DataAnalyzer(cpu_threshold=10, memory_threshold=10)
            analysis_results = analyzer.analyze_processes(processes_data)
            
            execution_time = time.time() - start_time
            
            # Create comprehensive result that includes both formats
            result = {
                'running_processes': {
                    'processes': simple_processes
                },
                'analysis': {
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'execution_time': execution_time,
                    'collection_duration': duration,
                    'snapshots_taken': snapshot_count,
                    'high_usage_processes': analysis_results
                }
            }
            
            logging.info(f"Process collection completed in {execution_time:.2f} seconds")
            logging.info(f"Found {len(simple_processes)} processes total")
            logging.info(f"High CPU processes: {len(analysis_results.get('cpu', []))}")
            logging.info(f"High memory processes: {len(analysis_results.get('memory', []))}")
            
            return result
            
        except Exception as e:
            logging.error(f"Critical error in get_running_processes: {str(e)}", exc_info=True)
            return {
                'running_processes': {
                    'processes': []
                },
                'error': str(e),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    @staticmethod
    def get_network_info():
        """
        Return current and nearby Wi-Fi networks grouped by security level.
        """
        def _is_wpa3_network(network) -> bool:
            """
            Check if a network is using WPA3 by examining both authentication and cipher.
            WPA3 uses SAE (8) for authentication and typically CCMP (4) for encryption.
            """
            try:
                auth_alg = network.akm[0] if network.akm else None
                cipher_type = network.cipher if hasattr(network, 'cipher') else None
                
                is_sae = auth_alg == 8
                is_ccmp = cipher_type == 4 if cipher_type is not None else False
                
                return is_sae and is_ccmp
            except Exception as e:
                logging.debug(f"Error checking WPA3: {str(e)}")
                return False
        
        def _determine_security_level(network) -> SecurityLevel:
            """Determine the security level of a network based on its authentication and cipher types."""
            try:
                auth_alg = network.akm[0] if network.akm else None
                cipher_type = network.cipher if hasattr(network, 'cipher') else None

                if auth_alg is None:
                    return SecurityLevel.NONE

                if _is_wpa3_network(network):
                    return SecurityLevel.WPA3
                elif auth_alg == const.AKM_TYPE_WPA2PSK or auth_alg == 4:
                    return SecurityLevel.WPA2
                elif auth_alg == const.AKM_TYPE_WPAPSK or auth_alg == 2:
                    return SecurityLevel.WPA
                elif auth_alg == 1 or cipher_type == const.CIPHER_TYPE_WEP:
                    return SecurityLevel.WEP
                elif auth_alg == const.AKM_TYPE_NONE or auth_alg == 0:
                    return SecurityLevel.NONE
                else:
                    logging.debug(f"Unknown security type: auth_alg={auth_alg}, cipher_type={cipher_type}")
                    return SecurityLevel.NONE
                    
            except Exception as e:
                logging.error(f"Error determining security level: {str(e)}, Network info: {network}")
                return SecurityLevel.NONE

        def _get_network_info(network, is_connected=False) -> NetworkInfo:
            """Convert pywifi network object to NetworkInfo."""
            security_level = _determine_security_level(network)
            requires_password = security_level != SecurityLevel.NONE
            
            ssid = network.ssid.strip() or "Hidden Network"

            return NetworkInfo(
                ssid=ssid,
                security_level=security_level,
                signal_strength=network.signal,
                requires_password=requires_password,
                is_connected=is_connected
            )

        try:
            wifi = pywifi.PyWiFi()
            interface = wifi.interfaces()[0]

            # Get current network
            current_network = None
            if interface.status() == const.IFACE_CONNECTED:
                current = interface.scan_results()[0]
                current_network = _get_network_info(current, is_connected=True)

            # Scan for available networks
            interface.scan()
            time.sleep(2)
            networks = interface.scan_results()
            
            networks_dict = {}
            
            for network in networks:
                network_info = _get_network_info(network)
                
                if (network_info.ssid not in networks_dict or 
                    network_info.signal_strength > networks_dict[network_info.ssid].signal_strength):
                    networks_dict[network_info.ssid] = network_info
            
            safe_networks = []
            unsafe_networks = []
            
            for network_info in networks_dict.values():
                if network_info.security_level in [SecurityLevel.WPA2, SecurityLevel.WPA3]:
                    safe_networks.append(network_info)
                else:
                    unsafe_networks.append(network_info)
            
            safe_networks.sort(
                key=lambda x: (x.security_level.value, x.signal_strength), 
                reverse=True
            )
            unsafe_networks.sort(
                key=lambda x: (x.security_level.value, x.signal_strength), 
                reverse=True
            )
            
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "current_network": current_network.to_dict() if current_network else None,
                "available_networks": {
                    "safe_networks": [n.to_dict() for n in safe_networks],
                    "unsafe_networks": [n.to_dict() for n in unsafe_networks]
                }
            }

        except Exception as e:
            logging.error(f"Error scanning networks: {str(e)}")
            return {
                "error": str(e),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }


    @staticmethod
    def get_storage_info():
        """Return disk usage for mounted partitions."""
        partitions = psutil.disk_partitions()
        storage_details = {}
        for partition in partitions:
            usage = psutil.disk_usage(partition.mountpoint)
            storage_details[partition.device] = {
                "total": f"{usage.total / (1024 ** 3):.2f} GB",
                "used": f"{usage.used / (1024 ** 3):.2f} GB",
                "free": f"{usage.free / (1024 ** 3):.2f} GB"
            }
        logging.info('Storage information fetched')
        return {"storage_details": storage_details}


    @staticmethod
    def get_peripherals_info():
        """Return connected USB/peripheral devices where the OS exposes them."""
        peripherals = {}
        if platform.system() == "Linux":
            import pyudev
            context = pyudev.Context()
            for device in context.list_devices(subsystem='usb'):
                device_info = {
                    "manufacturer": device.get('ID_VENDOR', 'Unknown'),
                    "model": device.get('ID_MODEL', 'Unknown')
                }
                peripherals[device.device_node] = device_info
        elif platform.system() == "Windows":
            pythoncom.CoInitialize()
            import wmi
            c = wmi.WMI()
            for usb in c.Win32_USBHub():
                peripherals[usb.DeviceID] = {"name": usb.Name}
        logging.info('Peripherals information fetched')
        return {"peripherals": peripherals}


    @staticmethod
    def get_installed_software_info():
        """Return installed software names and install dates when available."""
        programs = {}
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
            for i in range(winreg.QueryInfoKey(key)[0]):
                subkey = winreg.OpenKey(key, winreg.EnumKey(key, i))
                try:
                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    try:
                        install_date_raw = winreg.QueryValueEx(subkey, "InstallDate")[0]
                        formatted_date = datetime.strptime(install_date_raw, "%Y%m%d").strftime("%d/%m/%Y")
                        programs[display_name] = formatted_date
                    except FileNotFoundError:
                        programs[display_name] = ""
                except FileNotFoundError:
                    continue
        elif platform.system() == "Linux":
            result = subprocess.run(['dpkg', '--list'], stdout=subprocess.PIPE)
            program_lines = result.stdout.decode('utf-8').split('\n')
            for line in program_lines:
                if line.startswith('ii'):
                    program_name = line.split()[1]
                    programs[program_name] = program_name
        logging.info('Installed software information fetched')
        return {"installed_software": programs}
     
      
    @staticmethod
    def get_installed_software_recently():
        """Return software installed in the recent lookback window."""
        programs = {}
        if platform.system() == "Windows":
            try:
                time_threshold_days = 14
                time_threshold = datetime.now() - timedelta(days=time_threshold_days)
                key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                for i in range(winreg.QueryInfoKey(key)[0]):
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        try:
                            install_date_raw = winreg.QueryValueEx(subkey, "InstallDate")[0]
                            if len(str(install_date_raw)) == 8:
                                install_date = datetime.strptime(str(install_date_raw), "%Y%m%d")
                                if install_date >= time_threshold:
                                    programs[display_name] = install_date.strftime("%d/%m/%Y")
                        except FileNotFoundError:
                            pass
                    except FileNotFoundError:
                        continue
            except Exception as e:
                logging.warning(f"Error reading installed software info: {e}")
        logging.info('Recent downloads information fetched')
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "installed_software": programs
        }


    @staticmethod
    def get_recent_downloads():
        """Return recently modified files from browser download locations."""
        chrome_path = os.path.join(os.environ['LOCALAPPDATA'], "Google", "Chrome", "User Data")
        checked_folders = set()
        recent_files = {}
        time_threshold_days = 14
        time_threshold = (datetime.now() - timedelta(days=time_threshold_days)).timestamp()
        for folder in os.listdir(chrome_path):
            preferences_path = os.path.join(chrome_path, folder, "Preferences")
            if os.path.exists(preferences_path):
                try:
                    with open(preferences_path, 'r', encoding='utf-8') as f:
                        preferences = json.load(f)
                        download_folder = preferences.get("download", {}).get("default_directory",
                                                                            "Default folder not defined")
                        if download_folder == "Default folder not defined":
                            download_folder = os.path.join(os.environ['USERPROFILE'], 'Downloads')
                        if download_folder not in checked_folders and os.path.exists(download_folder):
                            checked_folders.add(download_folder)
                            for root, folders, files in os.walk(download_folder):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    modification_time = os.path.getmtime(file_path)
                                    if modification_time >= time_threshold:
                                        recent_files[file] = time.strftime("%d/%m/%Y %H:%M:%S",
                                                                        time.localtime(modification_time))
                except Exception as e:
                    logging.warning(f"Error processing download profile {folder}: {e}")
        logging.info('Recent downloads information fetched')
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "installed_files": recent_files
        }


    @staticmethod
    def get_cpu_info():
        """Return current CPU frequency and physical core count."""
        cpu_info = psutil.cpu_freq()
        cpu_count = psutil.cpu_count(logical=False)
        logging.info('CPU information fetched')
        return {"cpu_info": f"{cpu_info.current} MHz", "cpu_count": cpu_count}


    @staticmethod
    def get_browser_extensions():
        """Return Chrome extension names and versions from the default profile."""
        extensions = {}
        if platform.system() == "Windows":
            extensions_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Extensions")
            if os.path.exists(extensions_dir):
                for ext_id in os.listdir(extensions_dir):
                    ext_path = os.path.join(extensions_dir, ext_id)
                    if os.path.isdir(ext_path):
                        for version in os.listdir(ext_path):
                            manifest_path = os.path.join(ext_path, version, "manifest.json")
                            if os.path.exists(manifest_path):
                                with open(manifest_path, 'r', encoding='utf-8') as f:
                                    try:
                                        manifest = json.load(f)
                                        extension_name = manifest.get('name', 'Unknown')
                                        if extension_name not in extensions:
                                            extensions[extension_name] = []
                                        extensions[extension_name].append(version)
                                    except json.JSONDecodeError:
                                        pass
        logging.info('Browser extensions information fetched')
        return {"extensions": extensions}


    @staticmethod
    def get_defender_status():
        """Return Windows Defender status and recent categorized Defender logs."""
        if platform.system() != "Windows":
            return {"error": "This function is only supported on Windows."}
        
        try:
            pythoncom.CoInitialize()
            status = {}
            try:
                c_defender = wmi.WMI(namespace="root\\Microsoft\\Windows\\Defender")
                for product in c_defender.MSFT_MpComputerStatus():
                    status = {
                        "AMProductVersion": product.AMProductVersion,
                        "AMServiceEnabled": bool(product.AMServiceEnabled),
                        "AntivirusEnabled": bool(product.AntivirusEnabled),
                        "AntivirusSignatureVersion": product.AntivirusSignatureVersion,
                        "RealTimeProtectionEnabled": bool(product.RealTimeProtectionEnabled)
                    }
                    break
            except Exception as e:
                logging.error(f"Error fetching Defender WMI status: {str(e)}")
                status = {
                    "AMProductVersion": "Unknown",
                    "AMServiceEnabled": False,
                    "AntivirusEnabled": False,
                    "AntivirusSignatureVersion": "Unknown",
                    "RealTimeProtectionEnabled": False
                }

            start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            powershell_script = f"""
            $events = Get-WinEvent -LogName "Microsoft-Windows-Windows Defender/Operational" -ErrorAction SilentlyContinue |
                Where-Object {{ $_.TimeCreated -ge '{start_date}' }} |
                Select-Object TimeCreated, Id, Message

            if ($events) {{
                $events | ForEach-Object {{
                    @{{
                        TimeCreated = $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                        Id = $_.Id
                        Message = $_.Message
                    }}
                }} | ConvertTo-Json
            }} else {{
                Write-Output "[]"
            }}
            """

            result = subprocess.run(
                ['powershell', '-Command', powershell_script],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0 and result.stdout.strip():
                logs = json.loads(result.stdout)
                if not isinstance(logs, list):
                    logs = [logs]
            else:
                logs = []

            def format_defender_message(message: str) -> dict:
                """Format a Windows Defender log message as key/value fields."""
                lines = [line.strip() for line in message.split('\n') if line.strip()]
                
                formatted = {}
                
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        formatted[key] = value
                    else:
                        formatted['main'] = line.strip()
                        
                return formatted
            
            analyzer = DataAnalyzer()
            analyzed_logs = analyzer.analyze_defender_logs(logs)

            formatted_logs = {}
            for category, log_entries in analyzed_logs.items():
                formatted_logs[category] = []
                for entry in log_entries:
                    formatted_entry = entry.copy()
                    if 'message' in formatted_entry:
                        formatted_entry['message'] = format_defender_message(formatted_entry['message'])
                    formatted_logs[category].append(formatted_entry)
            
            return {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
                "logs": formatted_logs
            }

        except Exception as e:
            logging.error(f'Error in get_defender_status: {str(e)}')
            return {"error": str(e)}

    @staticmethod
    def get_firewall_status():
        """Return Windows Firewall profile status from netsh."""
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ['netsh', 'advfirewall', 'show', 'allprofiles'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                firewall_status = result.stdout
                logging.info('Firewall status fetched')
                return {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "firewall_status": firewall_status
                }
            except Exception as e:
                logging.error(f'Exception fetching firewall status: {str(e)}')
                return {"error": str(e)}


    @staticmethod
    def get_ram_info():
        """Return total and currently available RAM."""
        ram_info = psutil.virtual_memory()
        logging.info('RAM information fetched')
        return {
            "total_ram": f"{ram_info.total / (1024 ** 3):.2f} GB",
            "available_ram": f"{ram_info.available / (1024 ** 3):.2f} GB"
        }


    @staticmethod
    def get_gpu_info():
        """Return GPU names and driver versions."""
        gpus = GPUtil.getGPUs()
        gpu_details = {}
        for gpu in gpus:
            gpu_details[gpu.name] = gpu.driverVersion

        logging.info('GPU information fetched')
        return {"gpu_details": gpu_details}

    @staticmethod
    def _safe_command_execution(command: List[str]) -> subprocess.CompletedProcess:
        """Run a command without opening a console window on Windows."""
        
        if sys.platform == "win32":
            result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            result = subprocess.run(command, capture_output=True, text=True)
        
        return result


