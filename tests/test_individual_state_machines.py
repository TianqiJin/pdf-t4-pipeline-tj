"""Tests that the CDK stack creates the 3 individual state machines and outputs."""
import sys
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import assertions

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "infra"))

from stacks.pipeline_stack import PipelineStack


def _synth_template() -> assertions.Template:
    app = cdk.App()
    stack = PipelineStack(app, "TestStack")
    return assertions.Template.from_stack(stack)


def _sm_definition_strings(template: assertions.Template) -> list[str]:
    """Extract raw DefinitionString values (resolving Fn::Join) from all state machines."""
    raw = template.to_json()
    results = []
    for _lid, res in raw["Resources"].items():
        if res["Type"] != "AWS::StepFunctions::StateMachine":
            continue
        defn = res["Properties"].get("DefinitionString", "")
        if isinstance(defn, str):
            results.append(defn)
        elif isinstance(defn, dict) and "Fn::Join" in defn:
            parts = defn["Fn::Join"][1]
            results.append("".join(p for p in parts if isinstance(p, str)))
    return results


def test_three_individual_state_machines_exist():
    """Stack has 4 total state machines (1 pipeline + 3 individual)."""
    template = _synth_template()
    template.resource_count_is("AWS::StepFunctions::StateMachine", 4)


def test_split_only_state_machine_exists():
    template = _synth_template()
    definitions = _sm_definition_strings(template)
    assert any("SplitOnly" in d for d in definitions)


def test_parse_only_state_machine_exists():
    template = _synth_template()
    definitions = _sm_definition_strings(template)
    assert any("ParseOnly" in d for d in definitions)


def test_encrypt_only_state_machine_exists():
    template = _synth_template()
    definitions = _sm_definition_strings(template)
    assert any("EncryptOnly" in d for d in definitions)


def test_split_only_output_exists():
    template = _synth_template()
    template.has_output("SplitOnlyStateMachineArn", {})


def test_parse_only_output_exists():
    template = _synth_template()
    template.has_output("ParseOnlyStateMachineArn", {})


def test_encrypt_only_output_exists():
    template = _synth_template()
    template.has_output("EncryptOnlyStateMachineArn", {})
