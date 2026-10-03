import pytest
from unittest.mock import MagicMock

from pharmasense.agents.trial import create_trial_data_analyst
from pharmasense.agents.literature import create_literature_research_agent
from pharmasense.agents.adverse_event import create_ae_triage_agent
from pharmasense.agents.similarity import create_compound_similarity_agent
from pharmasense.agents.report import create_report_writer_agent

def test_trial_data_analyst_permissions():
    agent = create_trial_data_analyst(MagicMock(), MagicMock())
    assert "sql_query_tool" in agent.tools
    assert len(agent.tools) == 1

def test_literature_research_agent_permissions():
    agent = create_literature_research_agent(MagicMock(), MagicMock())
    assert "vector_search_tool" in agent.tools
    assert len(agent.tools) == 1

def test_ae_triage_agent_permissions():
    agent = create_ae_triage_agent(MagicMock(), MagicMock())
    assert "sql_query_tool" in agent.tools
    assert "ae_severity_classifier_tool" in agent.tools
    assert len(agent.tools) == 2

def test_compound_similarity_agent_permissions():
    agent = create_compound_similarity_agent(MagicMock(), MagicMock())
    assert "compound_similarity_tool" in agent.tools
    assert len(agent.tools) == 1

def test_report_writer_agent_permissions():
    agent = create_report_writer_agent(MagicMock(), MagicMock())
    assert "citation_formatter_tool" in agent.tools
    assert len(agent.tools) == 1

def test_agents_system_instructions():
    agent = create_ae_triage_agent(MagicMock(), MagicMock())
    assert "Adverse Event Triage" in agent.system_instruction
