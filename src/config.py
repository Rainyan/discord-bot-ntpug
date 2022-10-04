"""Module for reading the config preferences.

   Preferences are primarily read from the corresponding system environment
   variables, and from the config.yml config file as a fallback.
   Note that the type of the config values is enforced by the YAML schema.
"""

from ast import literal_eval
import os
import inspect


from strictyaml import (as_document, load, Bool, EmptyList, Float, Int, Map,
                        Seq, Str)

class PredicatedInt(Int):
    """StrictYAML Int validator, with optional predicates."""
    def __init__(self, predicates = None):
        self.predicates = predicates if predicates is not None else []

    def validate_scalar(self, chunk):
        val = super().validate_scalar(chunk)
        for pred in self.predicates:
            if not pred(val):
                chunk.expecting_but_found(str(inspect.getsourcelines(pred)[0]))
        return val


# The schema used for StrictYAML parsing.
YAML_CFG_SCHEMA = {
    "NTBOT_SECRET_TOKEN": Str(),
    "NTBOT_PUG_CHANNEL": Str(),
    "NTBOT_PLAYERS_REQUIRED_TOTAL": PredicatedInt([lambda x: x > 0,
                                                   lambda x: x % 2 == 0]),
    "NTBOT_DEBUG_ALLOW_REQUEUE": Bool(),
    "NTBOT_POLLING_INTERVAL_SECS": Int(),
    "NTBOT_PRESENCE_INTERVAL_SECS": Int(),
    "NTBOT_PUGGER_ROLE": Str(),
    "NTBOT_PUGGER_ROLE_PING_THRESHOLD": Float(),
    "NTBOT_PUGGER_ROLE_PING_MIN_INTERVAL_HOURS": Float(),
    "NTBOT_PUG_ADMIN_ROLES": Seq(Str()) | EmptyList(),
    "NTBOT_IDLE_THRESHOLD_HOURS": Float(),
    "NTBOT_PING_PUGGERS_COOLDOWN_SECS": Float(),
    "NTBOT_FIRST_TEAM_NAME": Str(),
    "NTBOT_SECOND_TEAM_NAME": Str(),
    "NTBOT_EPHEMERAL_MESSAGES": Bool(),

    "NTBOT_DB_DRIVER": Str(),
    "NTBOT_DB_NAME": Str(),
    "NTBOT_DB_USER": Str(),
    "NTBOT_DB_SECRET": Str(),
    "NTBOT_DB_TABLE": Str(),
    "NTBOT_DB_HOST": Str(),
    "NTBOT_DB_PORT": PredicatedInt([lambda x: x > 0]),
}
CFG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        "..", "cfg", "config.yml")
assert os.path.isfile(CFG_PATH)
with open(file=CFG_PATH, mode="r", encoding="utf-8") as f_config:
    CFG = load(f_config.read(), Map(YAML_CFG_SCHEMA))
assert CFG is not None

def cfg(key):
    """Returns a bot config value from environment variable or config file,
       in that order. If using an env var, its format has to match the type
       determined by the config values' StrictYAML schema.
    """
    assert isinstance(key, str)
    if os.environ.get(key):
        expected_ret_type = YAML_CFG_SCHEMA[key]
        # Small placeholder schema used for validating just this type.
        # We don't want to use the main schema because then we'd need
        # to populate it entirely, even though we're only interested
        # in returning this particular var.
        mini_schema = {key: expected_ret_type}
        # Generate StrictYAML in-place, with the mini-schema to enforce
        # strict typing, and then return the queried key's value.
        return as_document({key: literal_eval(os.environ.get(key))},
                           Map(mini_schema))[key].value
    return CFG[key].value
