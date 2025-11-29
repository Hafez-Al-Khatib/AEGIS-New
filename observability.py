import logging

logger = logging.getLogger("aegis")
logging.basicConfig(level=logging.INFO)

def log_api_call(func):
    # Decorator stub
    return func

def log_agent_event(agent_name, user_id, event, duration, extra=None):
    logger.info(f"Agent: {agent_name}, User: {user_id}, Event: {event}, Duration: {duration}ms, Extra: {extra}")
