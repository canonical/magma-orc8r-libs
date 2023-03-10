# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

import yaml
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Plan
from test_orc8r_base_charm.src.charm import (  # type: ignore[import]
    MagmaOrc8rDummyCharm,
    MagmaOrc8rDummyCharmWithRequiredRelation,
)


class TestCharm(unittest.TestCase):
    @patch(
        "test_orc8r_base_charm.src.charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,
    )
    def setUp(self):
        self.namespace = "banana"
        self.harness = testing.Harness(MagmaOrc8rDummyCharm)
        self.harness.set_model_name(self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_pebble_ready_when_get_pebble_plan_then_plan_is_filled_with_orc8r_service_content(  # noqa: E501
        self,
    ):
        expected_plan = {
            "services": {
                "magma-orc8r-dummy": {
                    "override": "replace",
                    "summary": "magma-orc8r-dummy",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/dummy "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-dummy",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                }
            },
        }
        self.harness.container_pebble_ready("magma-orc8r-dummy")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-dummy").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_pebble_plan_not_yet_set_when_pebble_ready_then_status_is_active(self):
        self.harness.container_pebble_ready("magma-orc8r-dummy")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("ops.model.Container.get_plan")
    def test_given_pebble_plan_already_set_when_pebble_ready_then_status_is_active(
        self, patch_get_plan
    ):
        pebble_plan = {
            "services": {
                "magma-orc8r-dummy": {
                    "override": "replace",
                    "summary": "magma-orc8r-dummy",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/dummy "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-dummy",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                }
            }
        }

        patch_get_plan.return_value = Plan(raw=yaml.dump(pebble_plan))
        self.harness.container_pebble_ready("magma-orc8r-dummy")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    def test_given_workload_not_running_when_relation_joined_then_service_status_is_marked_as_not_active_in_relation_data(  # noqa: E501
        self,
    ):
        self.harness.set_leader()

        relation_id = self.harness.add_relation(
            relation_name="magma-orc8r-dummy", remote_app="whatever"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="whatever/0")

        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.unit
        )
        expected_relation_data = {"active": "False"}
        self.assertEqual(expected_relation_data, relation_data)

    def test_given_workload_running_when_relation_joined_then_service_status_is_marked_as_active_in_relation_data(  # noqa: E501
        self,
    ):
        self.harness.set_leader()

        relation_id = self.harness.add_relation(
            relation_name="magma-orc8r-dummy", remote_app="whatever"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="whatever/0")
        self.harness.container_pebble_ready(container_name="magma-orc8r-dummy")

        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.unit
        )
        expected_relation_data = {"active": "True"}
        self.assertEqual(expected_relation_data, relation_data)

    def test_given_magma_orc8r_orchestrator_service_running_when_metrics_magma_orc8r_orchestrator_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        container = self.harness.model.unit.get_container("magma-orc8r-dummy")
        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(container)
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-dummy", "remote-app")
        self.harness.add_relation_unit(relation_id, "remote-app/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-dummy/0"),
            {"active": "True"},
        )

    def test_given_magma_orc8r_orchestrator_service_not_running_when_magma_orc8r_orchestrator_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-dummy", "remote-app")
        self.harness.add_relation_unit(relation_id, "remote-app/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-dummy/0"),
            {"active": "False"},
        )


class TestCharmWithRequiredRelation(unittest.TestCase):
    @patch(
        "test_orc8r_base_charm.src.charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rDummyCharmWithRequiredRelation)

        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.charm.PebbleReadyEvent.defer")
    def test_given_relation_is_not_created_when_pebble_ready_then_event_is_deferred(
        self, patch_defer
    ):
        event = Mock()

        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(event)

        patch_defer.assert_called()

    @patch("ops.charm.UpgradeCharmEvent.defer")
    def test_given_relation_is_not_created_when_upgrade_charm_then_event_is_deferred(
        self, patch_defer
    ):
        self.harness.charm.on.upgrade_charm.emit()

        patch_defer.assert_called()

    def test_given_relation_is_not_created_when_upgrade_charm_then_status_is_blocked(self):
        self.harness.charm.on.upgrade_charm.emit()

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-whatever"),
        )

    @patch("ops.charm.UpgradeCharmEvent.defer")
    def test_given_relation_created_but_not_ready_when_upgrade_charm_then_event_is_deferred(
        self, patch_defer
    ):
        self.harness.charm.on.upgrade_charm.emit()

        patch_defer.assert_called()

    def test_given_relation_created_but_not_ready_when_upgrade_charm_then_status_is_waiting(self):
        relation_id = self.harness.add_relation("magma-orc8r-whatever", "remote-app")
        self.harness.add_relation_unit(relation_id, "remote-app/0")

        self.harness.charm.on.upgrade_charm.emit()

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for relation(s) to be ready: magma-orc8r-whatever"),
        )

    def test_given_relation_created_and_ready_when_upgrade_charm_then_status_is_active(self):
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        relation_id = self.harness.add_relation("magma-orc8r-whatever", "remote-app")
        self.harness.add_relation_unit(relation_id, "remote-app/0")
        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="remote-app/0",
            key_values={"active": "True"},
        )

        self.harness.charm.on.upgrade_charm.emit()

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
