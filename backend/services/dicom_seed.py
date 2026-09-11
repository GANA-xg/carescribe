"""Generate a tiny valid DICOM file and load it into Orthanc on startup.

OC-06: "Load test DICOM into Orthanc on startup (use a public sample)".
A locally generated MRI-tagged sample is deterministic and offline —
better than a network fetch that can flake in CI. The file is stored at
/app/data/sample_mri.dcm and pushed to Orthanc if not already present.
"""
import io
import logging
import os
import uuid

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian

from services import orthanc

logger = logging.getLogger("carescribe.dicom_seed")

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sample_mri.dcm")

# Fixed so the seed is idempotent across restarts, and a valid UUID so it
# matches the /imaging/studies/{patient_id} path type.
SAMPLE_PATIENT_ID = "00000000-0000-4000-8000-000000000001"


def build_sample_dicom() -> bytes:
    """Minimal MRI-flavored DICOM instance (256x256 pixel array)."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.PatientName = "Seed^MRI^Sample"
    ds.PatientID = SAMPLE_PATIENT_ID
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.8.498.1"
    ds.SeriesInstanceUID = "1.2.826.0.1.3680043.8.498.2"
    ds.SOPInstanceUID = "1.2.826.0.1.3680043.8.498.3"
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture
    ds.Modality = "MR"
    ds.StudyDescription = "CareScribe seed MRI"
    ds.StudyDate = "20260911"
    ds.SeriesDescription = "T1 axial"
    ds.Rows = 256
    ds.Columns = 256
    ds.SamplesPerPixel = 1
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = bytes([i % 256 for i in range(256 * 256)])

    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


async def seed_orthanc() -> None:
    """Push the sample study into Orthanc once (idempotent)."""
    try:
        data = build_sample_dicom()
        os.makedirs(os.path.dirname(SAMPLE_PATH), exist_ok=True)
        with open(SAMPLE_PATH, "wb") as f:
            f.write(data)

        # Idempotency: check if our patient already exists.
        patients = await orthanc.list_patients()
        if SAMPLE_PATIENT_ID in patients:
            logger.info("orthanc seed already present")
            return

        result = await orthanc.upload_instance(data)
        logger.info("orthanc seeded: instance %s", result.get("ID"))
    except Exception:
        # Never block startup on the seeder.
        logger.exception("orthanc seeding failed (non-fatal)")
