# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

import yaml
from charms.magma_orc8r_libs.v1.orc8r_base_db import Orc8rBase
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Plan
from test_orc8r_base_db_charm_v1.src.charm import (  # type: ignore[import]
    MagmaOrc8rDummyCharm,
)


class TestCharm(unittest.TestCase):
    TEST_DB_NAME = Orc8rBase.DB_NAME
    DATABASE_DATABAG = {
        "database": TEST_DB_NAME,
        "endpoints": "123.456.679.012:1234",
        "username": "test_db_user",
        "password": "aaaBBBcccDDDeee",
    }

    @patch(
        "test_orc8r_base_db_charm_v1.src.charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,
    )
    def setUp(self):
        self.namespace = "banana"
        self.harness = testing.Harness(MagmaOrc8rDummyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_model_name(self.namespace)
        self.harness.set_leader(True)
        self.harness.begin_with_initial_hooks()

    @staticmethod
    def _fake_db_event(
        postgres_db_name: str,
        postgres_username: str,
        postgres_password: str,
        postgres_endpoints: str,
    ):
        db_event = Mock()
        db_event = Mock()
        db_event.database = postgres_db_name
        db_event.username = postgres_username
        db_event.password = postgres_password
        db_event.endpoints = postgres_endpoints
        return db_event

    @patch("ops.model.Unit.is_leader")
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self, is_leader
    ):
        is_leader.return_value = True
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )
        with patch.object(Orc8rBase, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                self.DATABASE_DATABAG["database"],
                self.DATABASE_DATABAG["username"],
                self.DATABASE_DATABAG["password"],
                self.DATABASE_DATABAG["endpoints"],
            )
            self.harness.charm._orc8r_base._configure_workload(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("psycopg2.connect", new=Mock())
    def test_given_pebble_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_dummy_service_content(  # noqa: E501
        self,
    ):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )

        self.harness.container_pebble_ready("magma-orc8r-dummy")

        expected_plan = {
            "services": {
                "magma-orc8r-dummy": {
                    "startup": "enabled",
                    "summary": "magma-orc8r-dummy",
                    "override": "replace",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/dummy "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "DATABASE_SOURCE": f"dbname={self.TEST_DB_NAME} "
                        f"user={self.DATABASE_DATABAG['username']} "
                        f"password={self.DATABASE_DATABAG['password']} "
                        f"host={self.DATABASE_DATABAG['endpoints']} "
                        f"sslmode=disable",
                        "SQL_DRIVER": "postgres",
                        "SQL_DIALECT": "psql",
                        "SERVICE_HOSTNAME": "magma-orc8r-dummy",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                },
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-dummy").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("psycopg2.connect", new=Mock())
    def test_given_pebble_plan_not_yet_set_when_pebble_ready_then_status_is_active(self):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )

        self.harness.container_pebble_ready("magma-orc8r-dummy")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("psycopg2.connect", new=Mock())
    @patch("ops.model.Container.get_plan")
    def test_given_pebble_plan_already_set_when_pebble_ready_then_status_is_active(
        self, patch_get_plan
    ):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )

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

    @patch("psycopg2.connect", new=Mock())
    def test_db_relation_added_when_get_status_then_status_is_active(self):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )

        self.harness.container_pebble_ready("magma-orc8r-dummy")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    def test_given_db_relation_not_created_when_pebble_ready_then_status_is_blocked(self):
        self.harness.container_pebble_ready(container_name="magma-orc8r-dummy")
        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for db relation to be created"
        )

    def test_given_db_relation_not_ready_when_pebble_ready_then_status_is_waiting(self):
        self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.container_pebble_ready(container_name="magma-orc8r-dummy")
        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for db relation to be ready"
        )

    @patch("psycopg2.connect", new=Mock())
    def test_given_pebble_ready_when_db_relation_broken_then_status_is_blocked(self):
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        container = self.harness.model.unit.get_container("magma-orc8r-dummy")
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )
        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(container)
        assert self.harness.charm.unit.status == ActiveStatus()

        self.harness.remove_relation(db_relation_id)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for db relation to be created"
        )

    @patch("psycopg2.connect", new=Mock())
    def test_given_magma_orc8r_dummy_service_running_when_metrics_magma_orc8r_dummy_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        container = self.harness.model.unit.get_container("magma-orc8r-dummy")
        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(container)
        relation_id = self.harness.add_relation("magma-orc8r-dummy", "remote-app")
        self.harness.add_relation_unit(relation_id, "remote-app/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-dummy/0"),
            {"active": "True"},
        )

    def test_given_magma_orc8r_dummy_service_not_running_when_magma_orc8r_dummy_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        relation_id = self.harness.add_relation("magma-orc8r-dummy", "remote-app")
        self.harness.add_relation_unit(relation_id, "remote-app/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-dummy/0"),
            {"active": "False"},
        )

    @patch("subprocess.check_call")
    def test_given_db_relation_not_created_when_upgrade_charm_then_status_is_blocked(
        self, patched_check_call
    ):
        patched_check_call.return_value = "whatever"

        self.harness.charm.on.upgrade_charm.emit()

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for db relation to be created"
        )

    @patch("ops.charm.UpgradeCharmEvent.defer")
    @patch("subprocess.check_call")
    def test_given_db_relation_not_created_when_upgrade_charm_then_event_is_deferred(
        self, patched_check_call, patch_defer
    ):
        patched_check_call.return_value = "whatever"

        self.harness.charm.on.upgrade_charm.emit()

        patch_defer.assert_called()

    @patch("subprocess.check_call")
    def test_given_db_relation_not_ready_when_upgrade_charm_then_status_is_waiting(
        self, patched_check_call
    ):
        patched_check_call.return_value = "whatever"
        self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")

        self.harness.charm.on.upgrade_charm.emit()

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for db relation to be ready"
        )

    @patch("ops.charm.UpgradeCharmEvent.defer")
    @patch("subprocess.check_call")
    def test_given_relation_created_but_not_ready_when_upgrade_charm_then_event_is_deferred(
        self, patched_check_call, patch_defer
    ):
        patched_check_call.return_value = "whatever"
        self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")

        self.harness.charm.on.upgrade_charm.emit()

        patch_defer.assert_called()

    @patch("psycopg2.connect", new=Mock())
    @patch("subprocess.check_call")
    def test_db_relation_added_when_upgrade_charm_then_status_is_active(self, patched_check_call):
        patched_check_call.return_value = "whatever"
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.update_relation_data(
            relation_id=db_relation_id,
            key_values=self.DATABASE_DATABAG,
            app_or_unit="postgresql-k8s",
        )

        self.harness.charm.on.upgrade_charm.emit()

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
