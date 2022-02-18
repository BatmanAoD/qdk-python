import unittest
import warnings

from azure.core.exceptions import HttpResponseError
from azure.quantum.aio.job.job import Job
from azure.quantum.aio.target import IonQ
from azure.quantum.aio.target.honeywell import Honeywell

from common import QuantumTestBase, ZERO_UID


class TestIonQ(QuantumTestBase):
    """TestIonq

    Tests the azure.quantum.target.ionq module.
    """

    mock_create_job_id_name = "create_job_id"
    create_job_id = Job.create_job_id

    def get_test_job_id(self):
        return ZERO_UID if self.is_playback \
               else Job.create_job_id()
    
    def _3_qubit_ghz(self):
        return {
            "qubits": 3,
            "circuit": [
                {
                "gate": "h",
                "target": 0
                },
                {
                "gate": "cnot",
                "control": 0,
                "target": 1
                },
                {
                "gate": "cnot",
                "control": 0,
                "target": 2
                },
            ]
        }

    def test_job_submit_ionq(self):
        self.get_async_result(self._test_job_submit_ionq(num_shots=None))

    def test_job_submit_ionq_100_shots(self):
        self.get_async_result(self._test_job_submit_ionq(num_shots=100))

    async def _test_job_submit_ionq(self, num_shots):

        with unittest.mock.patch.object(
            Job,
            self.mock_create_job_id_name,
            return_value=self.get_test_job_id(),
        ):
            workspace = self.create_async_workspace()
            circuit = self._3_qubit_ghz()
            target = IonQ(workspace=workspace)
            job = await target.submit(
                circuit=circuit,
                name="ionq-3ghz-job",
                num_shots=num_shots
            )

            # Make sure the job is completed before fetching the results
            # playback currently does not work for repeated calls
            # See: https://github.com/microsoft/qdk-python/issues/118
            self.pause_recording()
            try:
                # Set a timeout for IonQ recording
                await job.wait_until_completed(timeout_secs=60)
            except TimeoutError:
                warnings.warn("IonQ execution exceeded timeout. Skipping fetching results.")

            # Record a single GET request such that job.wait_until_completed
            # doesn't fail when running recorded tests
            # See: https://github.com/microsoft/qdk-python/issues/118
            await job.refresh()

            # Check if job succeeded
            self.assertEqual(True, job.has_completed())
            assert job.details.status == "Succeeded"
            self.resume_recording()

            job = await workspace.get_job(job.id)
            self.assertEqual(True, job.has_completed())

            results = await job.get_results()
            assert "histogram" in results
            assert results["histogram"]["0"] == 0.5
            assert results["histogram"]["7"] == 0.5

            if num_shots:
                assert job.details.input_params.get("shots") == num_shots
            else:
                assert job.details.input_params.get("shots") is None


class TestHoneywell(QuantumTestBase):
    mock_create_job_id_name = "create_job_id"
    create_job_id = Job.create_job_id

    def get_test_job_id(self):
        return ZERO_UID if self.is_playback \
               else Job.create_job_id()

    def _teleport(self):
        return """OPENQASM 2.0;
        include "qelib1.inc";

        qreg q[3];
        creg c0[1];
        creg c1[3];

        h q[0];
        cx q[0], q[1];
        x q[2];
        h q[2];
        cx q[2], q[0];
        h q[2];
        measure q[0] -> c1[0];
        c0[0] = c1[0];
        if (c0==1) x q[1];
        c0[0] = 0;
        measure q[2] -> c1[1];
        c0[0] = c1[1];
        if (c0==1) z q[1];
        c0[0] = 0;
        h q[1];
        measure q[1] -> c1[2];
        """

    def test_job_submit_honeywell(self):

        with unittest.mock.patch.object(
            Job,
            self.mock_create_job_id_name,
            return_value=self.get_test_job_id(),
        ):
            workspace = self.create_async_workspace()
            circuit = self._teleport()
            target = Honeywell(workspace=workspace)
            try:
                job = self.get_async_result( target.submit(circuit) )
            except HttpResponseError as e:
                if "InvalidJobDefinition" not in e.message \
                and "The provider specified does not exist" not in e.message:
                    raise(e)
                warnings.warn(e.message)
            else:
                # Make sure the job is completed before fetching the results
                # playback currently does not work for repeated calls
                if not self.is_playback:
                    self.assertEqual(False, job.has_completed())
                    try:
                        # Set a timeout for Honeywell recording
                        self.get_async_result( job.wait_until_completed(max_poll_wait_secs=60) )
                    except TimeoutError:
                        warnings.warn("Quantinuum (formerly Honeywell) execution exceeded timeout. Skipping fetching results.")
                    else:
                        # Check if job succeeded
                        self.assertEqual(True, job.has_completed())
                        assert job.details.status == "Succeeded"

                if job.has_completed():
                    results = self.get_async_result( job.get_results() )
                    assert results["c0"] == ["0"]
                    assert results["c1"] == ["000"]
