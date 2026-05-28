"""Main LangGraph workflow for the SecMate Confidence-Guided Orchestrator.

MessageHandler owns the Orchestrator-side decision graph: conversation
guardrails, diagnosis-confidence estimation, optional ClueCollector data
selection, follow-up question generation, profile-aware troubleshooting,
recommendation insertion, and per-node logging. External systems are accessed
through small service boundaries so release users can replace them with their
own implementations.
"""

from langchain.output_parsers.enum import EnumOutputParser
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from agent_state import AgentState, EmotionalState
from langgraph.graph import END, StateGraph
import json
import asyncio
from langchain_core.prompts import ChatPromptTemplate
import requests
import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
import time
import tiktoken
from dotenv import load_dotenv
import os
from typing import Any, Dict, Optional, TypedDict, List, Union
from service_clients import LoggerClient, UserProfileClient

from prompts import (
    SENTIMENT_ANALYZER_TEMPLATE,
    TS_ROUTER_TEMPLATE,
    TS_GEN_QUESTION_TEMPLATE,
    INTENT_ROUTER_TEMPLATE,
    NON_TROUBLESHOOTING_TEMPLATE,
    GEN_SOLUTION_CC_FALSE_ADAPTATION_TRUE_TEMPLATE,
    GEN_SOLUTION_CC_FALSE_ADAPTATION_FALSE_TEMPLATE,
    GEN_SOLUTION_CC_TRUE_ADAPTATION_TRUE_TEMPLATE,
    GEN_SOLUTION_CC_TRUE_ADAPTATION_FALSE_TEMPLATE,
    DIAGNOSIS_CONFIDENCE_CALCULATOR_TEMPLATE,
    SYSTEM_INFO_SELECTOR_TEMPLATE,
)

load_dotenv()


def build_service_url(service_name: str) -> str:
    """Build a service URL from direct or composed environment variables."""
    explicit_url = os.getenv(f"{service_name}_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    host = os.getenv("SERVICES_HOST")
    service = os.getenv(f"{service_name}_SERVICE")
    port = os.getenv(f"{service_name}_PORT")
    if not host or not service or not port:
        raise RuntimeError(
            f"Missing configuration for {service_name}. Set {service_name}_URL "
            f"or SERVICES_HOST, {service_name}_SERVICE, and {service_name}_PORT."
        )

    base_url = f"{host}{service}".rstrip("/")
    separator = "" if base_url.endswith(":") else ":"
    return f"{base_url}{separator}{port}"


class TokenCounter:
    def __init__(self):
        self.encoding = tiktoken.encoding_for_model("gpt-4")
    
    def count_tokens(self, text: Union[str, Dict, List]) -> int:
        """Count tokens in text, dict, or list input"""
        if isinstance(text, str):
            return len(self.encoding.encode(text))
        elif isinstance(text, dict):
            return self.count_dict_tokens(text)
        elif isinstance(text, list):
            return self.count_list_tokens(text)
        else:
            return 0
            
    def count_dict_tokens(self, data: Dict) -> int:
        """Count tokens in a dictionary by converting to JSON string"""
        return len(self.encoding.encode(json.dumps(data)))
        
    def count_list_tokens(self, data: List) -> int:
        """Count tokens in a list by converting to JSON string"""
        return len(self.encoding.encode(json.dumps(data)))
    
    def count_prompt_tokens(self, prompt: str, variables: Dict[str, Any]) -> int:
        """Count tokens in a prompt template with its variables"""
        filled_prompt = prompt
        for key, value in variables.items():
            filled_prompt = filled_prompt.replace(f"{{{key}}}", str(value))
            filled_prompt = filled_prompt.replace(f"{{key}}", str(value))
        
        return self.count_tokens(filled_prompt)


def calculate_prompt_usage(counter: TokenCounter, prompt: str, inputs: Dict[str, Any], output: Optional[str] = None) -> Dict[str, int]:
    """Calculate token usage for a specific prompt and its inputs/outputs"""
    prompt_tokens = counter.count_prompt_tokens(prompt, inputs)
    output_tokens = counter.count_tokens(output) if output else 0
    
    return {
        "input_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": prompt_tokens + output_tokens
    }


class MetricsLog(TypedDict):
    user_id: str
    conversation_id: str
    session_id: Optional[str]
    mid: str
    action_name: str
    step_number: int
    start_time: float
    end_time: float
    duration: float
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    timestamp: str


class LoggingClient:
    def __init__(self, logging_service_url: str):
        self.logging_service_url = logging_service_url
        self.action_endpoint = f"{logging_service_url}/action_log"
        self.metrics_endpoint = f"{logging_service_url}/metrics_log"
        
    def _make_serializable(self, data):
        """Make data JSON serializable"""
        if isinstance(data, dict):
            return {k: self._make_serializable(v) for k, v in data.items() if k != "password"}
        elif isinstance(data, list):
            return [self._make_serializable(item) for item in data]
        elif isinstance(data, Enum):
            return str(data.value)
        elif asyncio.iscoroutine(data):
            return "<coroutine>"
        elif hasattr(data, '_dict_'):
            return str(data)
        else:
            return data

    def log_action(self, 
                  user_id: str,
                  conversation_id: str,
                  session_id: str,
                  mid: str,
                  action_name: str,
                  step_number: int,
                  input_data: Dict[str, Any],
                  output_data: Dict[str, Any]) -> None:
        """Send one node-level action record to the configured logging service."""
        try:
            serializable_input = self._make_serializable(input_data)
            serializable_output = self._make_serializable(output_data)
            
            log_entry = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "mid": mid,
                "action_name": action_name,
                "step_number": step_number,
                "input_data": serializable_input,
                "output_data": serializable_output,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            requests.post(self.action_endpoint, json=log_entry, timeout=5)
        except Exception as e:
            logging.getLogger(__name__).warning("Failed to log action: %s", e)
        
    def log_metrics(self,
                   user_id: str,
                   conversation_id: str,
                   session_id: str,
                   mid: str,
                   action_name: str,
                   step_number: int,
                   start_time: float,
                   end_time: float,
                   duration: float,
                   input_tokens: Optional[int] = None,
                   output_tokens: Optional[int] = None,
                   total_tokens: Optional[int] = None) -> None:
        """Send timing and token metrics for one workflow node."""
        log_entry: MetricsLog = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "mid": mid,
            "action_name": action_name,
            "step_number": step_number,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            requests.post(self.metrics_endpoint, json=log_entry, timeout=5)
        except Exception as e:
            logging.getLogger(__name__).warning("Failed to log metrics: %s", e)


class MessageHandler:
    """Runs the troubleshooting workflow for a single chat turn."""
    
    def __init__(self, llm):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
        self.printer = logging.getLogger(__name__)
        self.printer.info("Logger initialized successfully")

        self.LOGGER_URL = build_service_url('LOGGER')
        self.logger = LoggingClient(self.LOGGER_URL)
        self.log_client = LoggerClient(self.LOGGER_URL)
        sent_parser = EnumOutputParser(enum=EmotionalState)
        self.AGENT_URL = build_service_url('AGENT')
        self.PROFILER_URL = build_service_url('PROFILER')
        self.profile_client = UserProfileClient(self.PROFILER_URL)
        self.RECOMMENDER_URL = build_service_url('RECOMMENDER')
        self.token_counter = TokenCounter()

        # Prompt chains used by LangGraph nodes.
        self.sentiment_analyzer_prompt = ChatPromptTemplate.from_template(SENTIMENT_ANALYZER_TEMPLATE)
        self.sentiment_analyzer = self.sentiment_analyzer_prompt | llm | sent_parser

        self.ts_router_prompt = ChatPromptTemplate.from_template(TS_ROUTER_TEMPLATE)
        self.ts_router = self.ts_router_prompt | llm | JsonOutputParser()

        self.ts_gen_question_prompt = ChatPromptTemplate.from_template(TS_GEN_QUESTION_TEMPLATE)
        self.ts_gen_question_chain = self.ts_gen_question_prompt | llm | StrOutputParser()

        self.intent_router_prompt = ChatPromptTemplate.from_template(INTENT_ROUTER_TEMPLATE)
        self.intent_router = self.intent_router_prompt | llm | JsonOutputParser()

        self.non_troubleshooting_prompt = ChatPromptTemplate.from_template(NON_TROUBLESHOOTING_TEMPLATE)
        self.non_troubleshooting_handler = self.non_troubleshooting_prompt | llm | StrOutputParser()

        self.diagnosis_confidence_prompt = ChatPromptTemplate.from_template(DIAGNOSIS_CONFIDENCE_CALCULATOR_TEMPLATE)
        self.diagnosis_confidence_calculator = self.diagnosis_confidence_prompt | llm | JsonOutputParser()

        self.system_info_selector_prompt = ChatPromptTemplate.from_template(SYSTEM_INFO_SELECTOR_TEMPLATE)
        self.system_info_selector = self.system_info_selector_prompt | llm | JsonOutputParser()

        self.gen_solution_cc_false_adaptation_true_prompt = ChatPromptTemplate.from_template(GEN_SOLUTION_CC_FALSE_ADAPTATION_TRUE_TEMPLATE)
        self.gen_solution_cc_false_adaptation_true_chain = self.gen_solution_cc_false_adaptation_true_prompt | llm | JsonOutputParser()

        self.gen_solution_cc_false_adaptation_false_prompt = ChatPromptTemplate.from_template(GEN_SOLUTION_CC_FALSE_ADAPTATION_FALSE_TEMPLATE)
        self.gen_solution_cc_false_adaptation_false_chain = self.gen_solution_cc_false_adaptation_false_prompt | llm | JsonOutputParser()

        self.gen_solution_cc_true_adaptation_true_prompt = ChatPromptTemplate.from_template(GEN_SOLUTION_CC_TRUE_ADAPTATION_TRUE_TEMPLATE)
        self.gen_solution_cc_true_adaptation_true_chain = self.gen_solution_cc_true_adaptation_true_prompt | llm | JsonOutputParser()

        self.gen_solution_cc_true_adaptation_false_prompt = ChatPromptTemplate.from_template(GEN_SOLUTION_CC_TRUE_ADAPTATION_FALSE_TEMPLATE)
        self.gen_solution_cc_true_adaptation_false_chain = self.gen_solution_cc_true_adaptation_false_prompt | llm | JsonOutputParser()

        self.app = self.setup_workflow()
        self.comprehensive_logs: List[Dict[str, Any]] = []

        self.prof_state = os.getenv("PROFILE_MODE", "high").lower()
        if self.prof_state not in {"high", "low", "real"}:
            self.printer.warning("Invalid PROFILE_MODE '%s'. Defaulting to 'high'.", self.prof_state)
            self.prof_state = "high"
        self.printer.info(f"Profile state set to: '{self.prof_state}'")

        self.high_profile = {
            "Hardware": {"General": 5, "Peripherals": 5, "Ram and Memory": 5, "Storage": 5},
            "Networking": {"Cloud Networking": 5, "Configuration": 5, "General": 5, "Protocols": 5, "Security": 5},
            "Other": {"General": 5},
            "Security": {"Authentication": 5, "Data Leakage": 5, "Encryption": 5, "General": 5, "Malware": 5, "Privacy": 5},
            "Software": {"App Management": 5, "General": 5, "Programming": 5, "Web Browsers": 5},
            "Operating_Systems": {"Drivers": 5, "File Management": 5, "General": 5, "Settings and Configurations": 5}
        }
        self.low_profile = {
            "Hardware": {"General": 1, "Peripherals": 1, "Ram and Memory": 1, "Storage": 1},
            "Networking": {"Cloud Networking": 1, "Configuration": 1, "General": 1, "Protocols": 1, "Security": 1},
            "Other": {"General": 1},
            "Security": {"Authentication": 1, "Data Leakage": 1, "Encryption": 1, "General": 1, "Malware": 1, "Privacy": 1},
            "Software": {"App Management": 1, "General": 1, "Programming": 1, "Web Browsers": 1},
            "Operating_Systems": {"Drivers": 1, "File Management": 1, "General": 1, "Settings and Configurations": 1}
        }

    def _get_profile_vector(self, user_id: str) -> Dict[str, Any]:
        """Return the active user proficiency profile for adaptation prompts."""
        if self.prof_state == "high":
            return self.high_profile
        if self.prof_state == "low":
            return self.low_profile

        profile = self.profile_client.get_profile(user_id)
        return profile or {}


    def __call__(self, user_query, history, sys_info, system_info_pull_count,
             user_id, conversation_id, mid, session_id, router_decision, diagnosis_confidence,
             performed_steps, connection_status, recommendation_timing, recommendation=None, recommendation_shown=False):

        inputs = {
            "user_query": user_query,
            "conversation_history": history,
            "system_info": sys_info,
            "system_info_pull_count": system_info_pull_count,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "mid": mid,
            "step_number": 0,
            "session_id": session_id,
            "router_decision": router_decision,
            "diagnosis_confidence": diagnosis_confidence,
            "performed_steps": performed_steps if performed_steps is not None else [],
            "selected_endpoints": None,
            "connection_status": connection_status,
            "recommendation_timing": recommendation_timing or self.recommendation_timing,
            "recommendation": recommendation,
            "recommendation_shown": recommendation_shown,
            "node_timings": {},
            "node_token_counts": {},
            "service_call_failures": []
        }

        final_state = self.app.invoke(inputs)

        ai_response_content = self._get_final_ai_response(final_state)

        system_info_to_log = final_state.get('system_info')
        if not system_info_to_log:
            system_info_to_log = "None"
        elif not isinstance(system_info_to_log, (str, dict, list)):
             system_info_to_log = str(system_info_to_log)

        recommendation_details_to_log = final_state.get('recommendation')
        if not recommendation_details_to_log:
            recommendation_details_to_log = "None"

        comprehensive_log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": final_state.get('user_id'),
            "conversation_id": final_state.get('conversation_id'),
            "session_id": final_state.get('session_id'),
            "user_query": final_state.get('user_query'),
            "ai_response": ai_response_content,
            "system_info": {"CC-Connection":final_state.get('connection_status'), "Confidence": final_state.get('diagnosis_confidence'), "System Info": system_info_to_log},
            "response_times_ms": final_state.get('node_timings', {}),
            "node_token_counts": final_state.get('node_token_counts', {}),
            "health_check_failures": final_state.get('service_call_failures', []),
            "recommendation_details": recommendation_details_to_log,
            "recommendation_shown_to_user": final_state.get('recommendation_shown', False),
            "prof_state": self.prof_state,
            "config_type": os.getenv('EXPERIMENT_CONFIG', 'clean-release')
        }

        self.printer.info(f"COMPREHENSIVE_LOG_ENTRY: {comprehensive_log_entry}")

        self.comprehensive_logs.append(comprehensive_log_entry)

        try:
            self.log_client.save_log_entry(
                user_id=final_state.get('user_id'),
                conversation_id=final_state.get('conversation_id'),
                log_entry=comprehensive_log_entry
            )
        except Exception as log_error:
            self.printer.error(f"Failed to save comprehensive log entry: {str(log_error)}")

        return final_state


    def setup_workflow(self):
        """Build the graph that processes one user message."""
        workflow = StateGraph(AgentState)
        workflow.add_node("analyze_sent", self.analyze_sent)
        workflow.add_node("route_query", self.route_query)
        workflow.add_node("handle_non_troubleshooting", self.handle_non_troubleshooting)
        workflow.add_node("calculate_diagnosis_confidence", self.calculate_diagnosis_confidence)
        workflow.add_node("gen_question", self.gen_question)
        
        cc_enabled_str = os.getenv('CC_ENABLED', 'false')
        adaptation_enabled_str = os.getenv('ADAPTATION_ENABLED', 'false')
        self.recommendation_timing = os.getenv('RECOMMENDATION_TIMING', 'late').lower()
        if self.recommendation_timing not in ['early', 'late']:
            self.printer.warning(f"Invalid RECOMMENDATION_TIMING value: {self.recommendation_timing}. Defaulting to 'late'")
            self.recommendation_timing = 'late'
        cc_enabled = cc_enabled_str.lower() == 'true'
        adaptation_enabled = adaptation_enabled_str.lower() == 'true'
        solution_method_to_use = None
        self.printer.info(f"Workflow Configuration: CC_ENABLED={cc_enabled}, ADAPTATION_ENABLED={adaptation_enabled}")
        
        if cc_enabled and adaptation_enabled:
            self.printer.info("Selecting solution method for: CC Enabled, Adaptation Enabled.")
            solution_method_to_use = self.gen_solution_cc_true_adaptation_true
        elif cc_enabled and not adaptation_enabled:
            self.printer.info("Selecting solution method for: CC Enabled, Adaptation Disabled.")
            solution_method_to_use = self.gen_solution_cc_true_adaptation_false
        elif not cc_enabled and adaptation_enabled:
            self.printer.info("Selecting solution method for: CC Disabled, Adaptation Enabled.")
            solution_method_to_use = self.gen_solution_cc_false_adaptation_true
        else:
            self.printer.info("Selecting solution method for: CC Disabled, Adaptation Disabled (General Solution).")
            solution_method_to_use = self.gen_solution_cc_false_adaptation_false
            
        if solution_method_to_use:
            workflow.add_node("gen_solution", solution_method_to_use)
            self.printer.info(f"Added 'gen_solution' node with method: {solution_method_to_use.__name__}")
        else:
            self.printer.error("Could not determine a solution generation method based on .env configuration. 'gen_solution' node not added.")

        workflow.add_node("select_system_info", self.select_system_info)
        workflow.add_node("execute_tool", self.execute_tools)

        workflow.set_entry_point("analyze_sent")

        workflow.add_conditional_edges(
            "analyze_sent",
            self.route_intent,
            {
                "troubleshooting": "calculate_diagnosis_confidence",
                "non_troubleshooting": "handle_non_troubleshooting"
            }
        )

        workflow.add_edge("calculate_diagnosis_confidence", "route_query")        
        workflow.add_conditional_edges(
            "route_query",
            self.get_router_decision,
            {
                "ask_followup_question": "gen_question",
                "solve_issue_general": "gen_solution",
                "request_system_info": "select_system_info",
            },
        )

        workflow.add_edge("select_system_info", "execute_tool")
        workflow.add_edge("execute_tool", "calculate_diagnosis_confidence")

        workflow.add_edge("handle_non_troubleshooting", END)
        workflow.add_edge("gen_question", END)
        workflow.add_edge("gen_solution", END)

        return workflow.compile()


    def calculate_diagnosis_confidence(self, state: AgentState):
        """Estimate whether enough evidence exists to ask, inspect, or solve."""
        action_name = 'calculate_diagnosis_confidence'
        performed_steps = state.get('performed_steps', [])
        if performed_steps is None: performed_steps = []
        performed_steps.append(action_name)
        step_number = state.get('step_number', 0) + 1
        
        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)
        
        input_data_for_chain = {
            "performed_steps": performed_steps,
            "user_query": state['user_query'],
            "conv_history": state["conversation_history"],
            "system_info": state['system_info']
        }
        
        confidence_result_json_str = self.diagnosis_confidence_calculator.invoke(input_data_for_chain)
        confidence_result_dict = json.loads(confidence_result_json_str) if isinstance(confidence_result_json_str, str) else confidence_result_json_str

        token_usage = calculate_prompt_usage(
            self.token_counter,
            DIAGNOSIS_CONFIDENCE_CALCULATOR_TEMPLATE,
            input_data_for_chain,
            json.dumps(confidence_result_dict)
        )
        
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
        
        self.logger.log_action(
            user_id=state['user_id'],
            conversation_id=state['conversation_id'],
            session_id=state['session_id'],
            mid=state['mid'],
            action_name=action_name,
            step_number=step_number,
            input_data={'performed_steps': performed_steps, 'user_query': state['user_query']},
            output_data={'diagnosis_confidence': confidence_result_dict['confidence']}
        )
        
        self.logger.log_metrics(
            user_id=state['user_id'],
            conversation_id=state['conversation_id'],
            session_id=state['session_id'],
            mid=state['mid'],
            action_name=action_name,
            step_number=step_number,
            start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(),
            duration=duration_ms,
            input_tokens=token_usage['input_tokens'],
            output_tokens=token_usage['output_tokens'],
            total_tokens=token_usage['total_tokens']
        )

        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms

        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return_value = {
            "diagnosis_confidence": confidence_result_dict['confidence'], 
            "step_number": step_number,
            "performed_steps": performed_steps,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts
        }
        return return_value


    def fetch_recommendation(self, user_id, conversation_history, timing='late', current_user_query=None, latest_assistant_response=None):
        """
        Fetch a product/service recommendation from the recommendation service.

        The returned value is kept as a small dictionary so downstream code can
        log it and optionally prepend its reasoning to the generated response.
        """
        serialized_conversation = []

        if isinstance(conversation_history, list):
            if len(conversation_history) > 0 and isinstance(conversation_history[0], dict) and "type" in conversation_history[0]:
                for msg in conversation_history:
                    if msg.get("type") == "human":
                        serialized_conversation.append(msg.get("content", ""))
                    else:
                        serialized_conversation.append({"response": msg.get("content", "")})
            else:
                for i in range(len(conversation_history)):
                    turn = conversation_history[i]
                    if i % 2 == 0:
                        if isinstance(turn, str):
                            serialized_conversation.append(turn)
                        elif hasattr(turn, 'content'):
                            serialized_conversation.append(turn.content)
                        else:
                            serialized_conversation.append(str(turn))
                    else:
                        if isinstance(turn, str):
                            serialized_conversation.append({"response": turn})
                        elif hasattr(turn, 'content'):
                            serialized_conversation.append({"response": turn.content})
                        elif isinstance(turn, dict) and "response" in turn:
                            serialized_conversation.append(turn)
                        else:
                            serialized_conversation.append({"response": str(turn)})

        if current_user_query:
            query_content = current_user_query
            if hasattr(current_user_query, 'content'):
                query_content = current_user_query.content
            elif not isinstance(current_user_query, str):
                query_content = str(current_user_query)
            serialized_conversation.append(query_content)

        if latest_assistant_response:
            response_content = latest_assistant_response
            if hasattr(latest_assistant_response, 'content'):
                response_content = latest_assistant_response.content
            elif isinstance(latest_assistant_response, dict) and 'response' in latest_assistant_response:
                response_content = latest_assistant_response['response']
            elif not isinstance(latest_assistant_response, str):
                response_content = str(latest_assistant_response)
            
            if response_content:
                serialized_conversation.append({"response": response_content})

        if not serialized_conversation:
            self.printer.warning("No conversation content for recommender user %s. Using placeholder.", user_id)
            serialized_conversation = ["I need help with my device"]
        
        recommendation = None
        
        try:
            payload = {
                "user_id": user_id,
                "conversation_history": serialized_conversation
            }
            
            self.printer.info("Fetching recommendation for user %s with timing %s", user_id, timing)
            
            response = requests.post(
                f"{self.RECOMMENDER_URL}/recommend",
                json=payload,
                timeout=500
            )

            response.raise_for_status()
            recommendation_data = response.json()

            if recommendation_data and recommendation_data.get("recommended_spc"):
                recommendation = {
                    "product": recommendation_data.get("recommended_spc"),
                    "reasoning": recommendation_data.get("reasoning"),
                    "description": recommendation_data.get("spc_description", "")[:200] + "..." if recommendation_data.get("spc_description") else "",
                    "details": recommendation_data.get("details")
                }
                self.printer.info("Recommendation received for user %s", user_id)
            else:
                self.printer.info("No recommendation returned for user %s", user_id)
        
        except Exception as e:
            self.printer.error("Error fetching recommendation: %s", str(e))
            return None
        
        return recommendation


    def route_intent(self, state: AgentState):
        """Classify whether the user turn is troubleshooting-related."""
        action_name = 'route_intent'
        performed_steps = state['performed_steps']
        performed_steps.append(action_name)
        step_number = state['step_number'] + 1
        
        gmt2 = timezone(timedelta(hours=2))
        start_time = time.perf_counter()
        start_timestamp = datetime.now(gmt2)

        input_data = {
            "user_query": state["user_query"],
            "conv_hist": state["conversation_history"],
            "emotional_state": state["emotional_state"]
        }

        router_result = self.intent_router.invoke(input_data)
        
        end_time = time.perf_counter()
        duration = round((end_time - start_time) * 1000, 2)
        end_timestamp = datetime.now(gmt2)
        
        self.logger.log_action(
            user_id=state['user_id'],
            conversation_id=state['conversation_id'],
            session_id=state['session_id'],
            mid=state['mid'],
            action_name='route_intent',
            step_number=step_number,
            input_data=input_data,
            output_data={'intent_decision': router_result['intent_decision']}
        )
        
        self.logger.log_metrics(
            user_id=state['user_id'],
            conversation_id=state['conversation_id'],
            session_id=state['session_id'],
            mid=state['mid'],
            action_name='route_intent',
            step_number=step_number,
            start_time=start_timestamp.isoformat(),
            end_time=end_timestamp.isoformat(),
            duration=duration,
        )

        return router_result['intent_decision']


    def handle_non_troubleshooting(self, state: AgentState):
        """Generate a response for turns outside the troubleshooting workflow."""
        action_name = 'handle_non_troubleshooting'
        performed_steps = state.get('performed_steps', [])
        if performed_steps is None: performed_steps = []
        performed_steps.append(action_name)
        step_number = state.get('step_number', 0) + 1
        
        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)

        input_data_for_chain = {
            "user_query": state["user_query"],
            "conv_hist": state["conversation_history"],
            "emotional_state": state["emotional_state"]
        }

        output_str_from_llm = self.non_troubleshooting_handler.invoke(input_data_for_chain)

        token_usage = calculate_prompt_usage(
            self.token_counter,
            NON_TROUBLESHOOTING_TEMPLATE,
            input_data_for_chain,
            output_str_from_llm
        )

        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
        
        self.logger.log_action(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='handle_non_troubleshooting', step_number=step_number,
            input_data=input_data_for_chain, output_data={'response': output_str_from_llm}
        )
        self.logger.log_metrics(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='handle_non_troubleshooting', step_number=step_number, start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(), duration=duration_ms
        )

        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage
        return {
            "response": output_str_from_llm,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "augmented_question": output_str_from_llm,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts
        }


    def analyze_sent(self, state: AgentState):
        """Estimate the user's emotional state before intent routing."""
        action_name = 'analyze_sent'
        performed_steps = state.get('performed_steps', [])
        if performed_steps is None: performed_steps = []
        performed_steps.append(action_name)
        step_number = state.get('step_number', 0) + 1

        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)

        input_data_for_chain = {
            "client_message": state['user_query'],
            "format_instructions": "respond by number only"
        }

        sentiment_enum_obj = self.sentiment_analyzer.invoke(input_data_for_chain)
        output_str_from_llm = str(sentiment_enum_obj.value)

        token_usage = calculate_prompt_usage(
            self.token_counter,
            SENTIMENT_ANALYZER_TEMPLATE,
            input_data_for_chain,
            output_str_from_llm
        )
        
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
        
        self.logger.log_action(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='analyze_sent', step_number=step_number,
            input_data={'user_query': state['user_query']}, output_data={'sentiment': output_str_from_llm}
        )
        self.logger.log_metrics(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='analyze_sent', step_number=step_number, start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(), duration=duration_ms
        )

        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "emotional_state": sentiment_enum_obj, 
            "step_number": step_number, 
            "performed_steps": performed_steps,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts
        }


    def _handle_recommendation(self, state: AgentState, agent_response: str, allowed_timings: list[str]):
        """Fetch and prepend a recommendation when the configured timing allows it."""
        recommendation_shown = state.get('recommendation_shown', False)
        current_recommendation = state.get('recommendation')
        timing = state.get('recommendation_timing')

        if timing in allowed_timings and not recommendation_shown:
            fetch_args = {
                'user_id': state['user_id'],
                'conversation_history': state['conversation_history'],
                'timing': timing,
                'current_user_query': state['user_query']
            }
            if timing == 'late':
                fetch_args['latest_assistant_response'] = agent_response

            new_recommendation = self.fetch_recommendation(**fetch_args)

            if new_recommendation and new_recommendation.get('reasoning'):
                recommendation_text = new_recommendation.get('reasoning')
                formatted_response = (
                    f"**Especially for you:**\n{recommendation_text}"
                    f"\n\n---\n\n"
                    f"{agent_response}"
                )
                return formatted_response, True, new_recommendation

        return agent_response, recommendation_shown, current_recommendation


    def gen_question(self, state: AgentState):
        """Generate the next follow-up question when confidence is not high enough."""
        action_name = 'gen_question'
        performed_steps = state.get('performed_steps', [])
        if performed_steps is None: performed_steps = []
        performed_steps.append(action_name)
        step_number = state.get('step_number', 0) + 1
        
        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)

        prof = self._get_profile_vector(state['user_id'])
        
        input_data_for_chain = {
            "user_query": state['user_query'],
            "conversation_history": state['conversation_history'],
            "system_info": state['system_info'],
            "user_proficiency_vector": prof,
        }

        generated_question_from_llm = self.ts_gen_question_chain.invoke(input_data_for_chain)
        
        token_usage = calculate_prompt_usage(
            self.token_counter,
            TS_GEN_QUESTION_TEMPLATE,
            input_data_for_chain,
            generated_question_from_llm
        )

        final_question_to_user, recommendation_shown_updated, current_recommendation_object = self._handle_recommendation(
            state,
            generated_question_from_llm,
            ['early']
        )
        
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
        
        log_action_input_data = {
            'user_query': state['user_query'], 'system_info': state['system_info'],
            'conversation_history': state['conversation_history']
        }
        self.logger.log_action(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='gen_question', step_number=step_number,
            input_data=log_action_input_data, output_data={'question': final_question_to_user}
        )
        self.logger.log_metrics(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='gen_question', step_number=step_number, start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(), duration=duration_ms
        )

        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "ts_question": final_question_to_user,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "augmented_question": final_question_to_user,
            "recommendation": current_recommendation_object,
            "recommendation_shown": recommendation_shown_updated,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts
        }


    def gen_solution_cc_false_adaptation_true(self, state: AgentState):
        """
        Generates a solution when CC is disconnected but adaptation is enabled.
        (Personalized solution without live system data)
        """
        action_name = 'gen_solution'
        performed_steps = state['performed_steps']
        performed_steps.append(action_name)
        step_number = state['step_number'] + 1
        
        start_time_perf = time.perf_counter()
        
        prof = self._get_profile_vector(state['user_id'])
        self.printer.info(f"User proficiency vector: {prof}")

        input_data = {
            "user_query": state['user_query'],
            "conversation_history": state['conversation_history'],
            "user_proficiency_vector": prof,
        }
        
        try:
            solution = self.gen_solution_cc_false_adaptation_true_chain.invoke(input_data)
            if solution is None:
                raise ValueError("Solution generation returned None")
        except Exception as e:
            self.printer.error(f"Error in gen_solution_cc_false_adaptation_true: {str(e)}")
            solution = {
                "diagnosis": "Error Generating Solution",
                "explanation": "I apologize, but I encountered an error while trying to find a solution.",
                "action_steps": ["Please try describing your issue again."]
            }
        
        output_json_for_tokens = json.dumps(solution)
        token_usage = calculate_prompt_usage(
            self.token_counter, 
            GEN_SOLUTION_CC_FALSE_ADAPTATION_TRUE_TEMPLATE,
            input_data,
            output_json_for_tokens
        )

        formatted_solution = self.format_solution_for_display(solution)
        
        augmented_solution, recommendation_shown_updated, current_recommendation_object = self._handle_recommendation(
            state,
            formatted_solution,
            ['early', 'late']
        )
        
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        
        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "augmented_solution": augmented_solution,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "recommendation": current_recommendation_object,
            "recommendation_shown": recommendation_shown_updated,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts,
        }


    def gen_solution_cc_true_adaptation_false(self, state: AgentState):
        """
        Generates a solution when CC is connected but adaptation is disabled.
        (General solution using live system data)
        """
        action_name = 'gen_solution'
        performed_steps = state['performed_steps']
        performed_steps.append(action_name)
        step_number = state['step_number'] + 1
        
        start_time_perf = time.perf_counter()

        input_data = {
            "user_query": state['user_query'],
            "system_info": state['system_info'],
            "conversation_history": state['conversation_history'],
        }
        
        try:
            solution = self.gen_solution_cc_true_adaptation_false_chain.invoke(input_data)
            if solution is None:
                raise ValueError("Solution generation returned None")
        except Exception as e:
            self.printer.error(f"Error in gen_solution_cc_true_adaptation_false: {str(e)}")
            solution = {
                "diagnosis": "Error Generating Solution",
                "explanation": "I apologize, but I encountered an error while trying to find a solution.",
                "action_steps": ["Please try describing your issue again."]
            }
        
        output_json_for_tokens = json.dumps(solution)
        token_usage = calculate_prompt_usage(
            self.token_counter, 
            GEN_SOLUTION_CC_TRUE_ADAPTATION_FALSE_TEMPLATE,
            input_data,
            output_json_for_tokens
        )
        
        formatted_solution = self.format_solution_for_display(solution)

        augmented_solution, recommendation_shown_updated, current_recommendation_object = self._handle_recommendation(
            state,
            formatted_solution,
            ['early', 'late']
        )
        
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        
        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "augmented_solution": augmented_solution,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "recommendation": current_recommendation_object,
            "recommendation_shown": recommendation_shown_updated,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts,
        }


    def gen_solution_cc_true_adaptation_true(self, state: AgentState):
        """
        Generates a solution when CC is connected and adaptation is enabled.
        (Personalized solution using live system data)
        """
        action_name = 'gen_solution'
        performed_steps = state['performed_steps']
        performed_steps.append(action_name)
        step_number = state['step_number'] + 1
        
        start_time_perf = time.perf_counter()

        prof = self._get_profile_vector(state['user_id'])
        self.printer.info(f"User proficiency vector: {prof}")

        input_data = {
            "user_query": state['user_query'],
            "system_info": state['system_info'],
            "conversation_history": state['conversation_history'],
            "user_proficiency_vector": prof,
        }
        
        try:
            solution = self.gen_solution_cc_true_adaptation_true_chain.invoke(input_data)
            if solution is None:
                raise ValueError("Solution generation returned None")
        except Exception as e:
            self.printer.error(f"Error in gen_solution_cc_true_adaptation_true: {str(e)}")
            solution = {
                "diagnosis": "Error Generating Solution",
                "explanation": "I apologize, but I encountered an error while trying to find a solution.",
                "action_steps": ["Please try describing your issue again."]
            }
        
        output_json_for_tokens = json.dumps(solution)
        token_usage = calculate_prompt_usage(
            self.token_counter, 
            GEN_SOLUTION_CC_TRUE_ADAPTATION_TRUE_TEMPLATE,
            input_data,
            output_json_for_tokens
        )
        
        formatted_solution = self.format_solution_for_display(solution)
        
        augmented_solution, recommendation_shown_updated, current_recommendation_object = self._handle_recommendation(
            state,
            formatted_solution,
            ['early', 'late']
        )

        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        
        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "augmented_solution": augmented_solution,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "recommendation": current_recommendation_object,
            "recommendation_shown": recommendation_shown_updated,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts,
        }


    def gen_solution_cc_false_adaptation_false(self, state: AgentState):
        """
        Generates a solution when CC is disconnected and adaptation is disabled.
        (General solution without personalization or live system data)
        """
        action_name = 'gen_solution'
        performed_steps = state['performed_steps']
        performed_steps.append(action_name)
        step_number = state['step_number'] + 1
        
        start_time_perf = time.perf_counter()
        
        input_data = {
            "user_query": state['user_query'],
            "conversation_history": state['conversation_history'],
        }
        
        try:
            solution = self.gen_solution_cc_false_adaptation_false_chain.invoke(input_data)
            if solution is None:
                raise ValueError("Solution generation returned None")
        except Exception as e:
            self.printer.error(f"Error in gen_solution_cc_false_adaptation_false: {str(e)}")
            solution = {
                "diagnosis": "Error Generating Solution",
                "explanation": "I apologize, but I encountered an error while trying to find a solution.",
                "action_steps": ["Please try describing your issue again."]
            }
        
        output_json_for_tokens = json.dumps(solution)
        token_usage = calculate_prompt_usage(
            self.token_counter, 
            GEN_SOLUTION_CC_FALSE_ADAPTATION_FALSE_TEMPLATE,
            input_data,
            output_json_for_tokens
        )
        
        formatted_solution = self.format_solution_for_display(solution)
        
        augmented_solution, recommendation_shown_updated, current_recommendation_object = self._handle_recommendation(
            state,
            formatted_solution,
            ['early', 'late']
        )

        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        
        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "augmented_solution": augmented_solution,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "recommendation": current_recommendation_object,
            "recommendation_shown": recommendation_shown_updated,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts,
        }


    def format_solution_for_display(self, solution):
        """Convert a solution dictionary or string to a natural language response"""
        try:
            if isinstance(solution, str):
                return solution
            
            if isinstance(solution, dict):
                diagnosis = solution.get("diagnosis", "")
                explanation = solution.get("explanation", "")
                action_steps = solution.get("action_steps", [])
                
                formatted = f"**{diagnosis}**\n\n{explanation}\n\n"
                
                if action_steps:
                    formatted += "Here are the steps to resolve this issue:\n\n"
                    for i, step in enumerate(action_steps, 1):
                        formatted += f"{i}. {step}\n"
                
                return formatted
            
            return str(solution)
        except Exception as e:
            self.printer.error(f"Error formatting solution: {str(e)}")
            self.printer.error(f"Solution type: {type(solution)}")
            self.printer.error(f"Solution value: {str(solution)[:100]}...")
            return "I apologize, but I encountered an error formatting your solution."
    

    def route_query(self, state: AgentState):
        """Choose whether to ask, solve, or request ClueCollector data next."""
        action_name = 'route_query'
        step_number = state.get('step_number', 0) + 1 
    
        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)

        performed_steps_for_input = state.get('performed_steps', [])

        select_system_info_count = performed_steps_for_input.count("select_system_info")
        excessive_system_info_calls = select_system_info_count >= 3
        gen_question_count = performed_steps_for_input.count("gen_question")
        excessive_gen_questions = gen_question_count >= 3

        input_data_for_chain = {
            "user_query": state["user_query"],
            "conv_hist": state["conversation_history"],
            "performed_steps": performed_steps_for_input,
            "diagnosis_confidence": state['diagnosis_confidence'],
            "connection_status": state['connection_status'],
            "system_info": state['system_info']
        }

        router_result_dict = self.ts_router.invoke(input_data_for_chain)
        output_json_str_from_llm = json.dumps(router_result_dict)

        token_usage = calculate_prompt_usage(
            self.token_counter,
            TS_ROUTER_TEMPLATE,
            input_data_for_chain,
            output_json_str_from_llm
        )
        
        original_router_decision = router_result_dict['router_decision'] 
        current_router_decision = original_router_decision

        if excessive_system_info_calls and current_router_decision == "request_system_info":
            current_router_decision = "solve_issue"
        elif excessive_gen_questions and current_router_decision == "ask_followup_question":
            current_router_decision = "solve_issue"

        final_decision = current_router_decision
        
        if final_decision == "solve_issue":
            final_decision = "solve_issue_general"
    
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
    
        self.logger.log_action(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='route_query', step_number=step_number,
            input_data=input_data_for_chain,
            output_data={'router_decision': final_decision}
        )
        self.logger.log_metrics(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='route_query', step_number=step_number, start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(), duration=duration_ms
        )
        
        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage
        
        return {
            "router_decision": final_decision,
            "step_number": step_number,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts,
            "performed_steps": state.get('performed_steps', [])
        }


    def get_router_decision(self, state):
        """Return the route selected by the route_query node."""
        decision = state['router_decision']
        if decision == None:
            decision = "ask_followup_question"
        self.printer.info(f"Routing decision from state: {decision}")

        return decision


    def select_system_info(self, state: AgentState):
        """Select which ClueCollector endpoints are relevant for the current issue."""
        action_name = 'select_system_info'
        performed_steps = state.get('performed_steps', [])
        if performed_steps is None: performed_steps = []
        performed_steps.append(action_name) 
        step_number = state.get("step_number", 0) + 1
        
        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)

        input_data_for_chain = {
            "user_query": state["user_query"],
            "conv_hist": state["conversation_history"],
            "performed_steps": state.get("performed_steps", []),
            "diagnosis_confidence": state["diagnosis_confidence"]
        }

        selector_result_dict = self.system_info_selector.invoke(input_data_for_chain)
        selected_endpoints_list = selector_result_dict.get('selected_endpoints', [])

        output_json_str_for_tokens = json.dumps(selector_result_dict)
        token_usage = calculate_prompt_usage(
            self.token_counter, 
            SYSTEM_INFO_SELECTOR_TEMPLATE,
            input_data_for_chain,
            output_json_str_for_tokens
        )
        
        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
        
        self.logger.log_action(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='select_system_info', step_number=step_number,
            input_data=input_data_for_chain, output_data={'selected_endpoints': selected_endpoints_list}
        )
        self.logger.log_metrics(
            user_id=state['user_id'], conversation_id=state['conversation_id'], session_id=state['session_id'], mid=state['mid'],
            action_name='select_system_info', step_number=step_number, start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(), duration=duration_ms
        )

        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms
        current_token_counts = state.get('node_token_counts', {}).copy()
        current_token_counts[action_name] = token_usage

        return {
            "selected_endpoints": selected_endpoints_list,
            "performed_steps": performed_steps,
            "step_number": step_number,
            "node_timings": current_timings,
            "node_token_counts": current_token_counts
        }  


    def execute_tools(self, state: AgentState):
        """Call the agent-service bridge for the selected ClueCollector data."""
        action_name = 'execute_tools'
        performed_steps = state.get('performed_steps', [])
        if performed_steps is None: performed_steps = []
        performed_steps.append(action_name)
        step_number = state.get('step_number', 0) + 1
                    
        gmt2 = timezone(timedelta(hours=2))
        start_time_perf = time.perf_counter()
        start_timestamp_metric = datetime.now(gmt2)

        endpoints_to_call = state.get('selected_endpoints')
        if not isinstance(endpoints_to_call, list):
            endpoints_to_call = []

        collected_system_info, new_failures = self.request_system_info(state['user_id'], endpoints_to_call)

        end_time_perf = time.perf_counter()
        duration_ms = round((end_time_perf - start_time_perf) * 1000, 2)
        end_timestamp_metric = datetime.now(gmt2)
        
        self.logger.log_action(
            user_id=state['user_id'],
            conversation_id=state['conversation_id'],
            session_id=state['session_id'],
            mid=state['mid'],
            action_name=action_name,
            step_number=step_number,
            input_data={'user_id': state['user_id'], 'selected_endpoints_for_call': endpoints_to_call},
            output_data={'system_info_collected': collected_system_info}
        )
        
        self.logger.log_metrics(
            user_id=state['user_id'],
            conversation_id=state['conversation_id'],
            session_id=state['session_id'],
            mid=state['mid'],
            action_name=action_name,
            step_number=step_number,
            start_time=start_timestamp_metric.isoformat(),
            end_time=end_timestamp_metric.isoformat(),
            duration=duration_ms
        )

        current_timings = state.get('node_timings', {}).copy()
        current_timings[action_name] = duration_ms

        all_failures = state.get('service_call_failures', []).copy()
        all_failures.extend(new_failures)

        return_value = {
            "system_info": collected_system_info,
            "step_number": step_number,
            "performed_steps": performed_steps,
            "node_timings": current_timings,
            "service_call_failures": all_failures
        }
        return return_value


    def _make_request(self, user_id: str, endpoint: str):
        """Send one ClueCollector action request through the agent-service bridge."""
        try:
            response = requests.post(
                f"{self.AGENT_URL}/forward_request",
                json={"uid": user_id, "action": endpoint},
                timeout=100.0
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "error", 
                    "endpoint_called": endpoint, 
                    "status_code": response.status_code,
                    "message": f"Request to agent for action {endpoint} failed.",
                    "details": response.text[:500] 
                }
        except requests.exceptions.RequestException as e:
            return {
                "status": "connection_failed", 
                "endpoint_called": endpoint,
                "error": str(e), 
                "message": f"Connection failed for action {endpoint}."
            }
        except Exception as e: 
            return {
                "status": "unexpected_error",
                "endpoint_called": endpoint,
                "error": str(e),
                "message": f"An unexpected error occurred during request for action {endpoint}."
            }


    def request_system_info(self, user_id, selected_endpoints):
        """Collect the requested ClueCollector endpoint results."""
        info_endpoints = [
            "cpu_info", "os_info", "ram_info", "gpu_info", "storage_info",
            "peripherals_info", "installed_software_info", "browser_extensions",
            "firewall_status", "defender_status", "open_ports", "running_processes",
            "installed_software_recently", "recent_downloads", "network_info"
        ]

        system_info_data = {}
        failures = []
        if not selected_endpoints:
            return system_info_data, failures

        for endpoint in selected_endpoints:
            if endpoint in info_endpoints:
                result = self._make_request(user_id, endpoint)
                if isinstance(result, dict) and result.get("status") in ["error", "connection_failed", "unexpected_error"]:
                    failures.append({
                        "service": "AGENT_SERVICE_TOOL_EXECUTION",
                        "tool_or_endpoint_requested": endpoint,
                        "failure_type": result.get("status"),
                        "message": result.get("message"),
                        "details": result 
                    })
                else:
                    system_info_data[endpoint] = result
        return system_info_data, failures


    def _get_final_ai_response(self, result_state: AgentState) -> str:
        """Extract the final response from the Orchestrator state."""
        if result_state.get('augmented_solution'):
            solution = result_state['augmented_solution']
            return solution if isinstance(solution, str) else json.dumps(solution, default=str)
        if result_state.get('augmented_question'):
            return result_state['augmented_question']
        if result_state.get('response'):
            return result_state['response']
        if result_state.get('ts_solution'): 
             return json.dumps(result_state['ts_solution'], default=str)
        if result_state.get('ts_question'): 
             return result_state['ts_question']
        return "No specific AI response identified in final state."
