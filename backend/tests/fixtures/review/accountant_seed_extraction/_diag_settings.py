from payroll_copilot.infrastructure.config.ollama_resolver import get_resolved_ollama_base_url
from payroll_copilot.infrastructure.config.settings import get_settings

s = get_settings()
print("payslip_parser_model", repr(s.payslip_parser_model))
print("ollama_default_model", repr(s.ollama_default_model))
print("layout", s.payslip_parser_layout_enabled)
print("json_fmt", s.payslip_parser_use_json_format)
print("temp", s.payslip_parser_temperature)
print("timeout", s.payslip_parser_timeout_seconds)
print("base", get_resolved_ollama_base_url(s))
