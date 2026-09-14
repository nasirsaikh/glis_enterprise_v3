# Generated data migration from the uploaded updated GLIS content snapshot (2026-09-14).
from pathlib import Path
import json
import gzip
from django.db import migrations

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_FILES = [DATA_DIR / f"updated_site_content_20260914_{i}.json.gz" for i in range(1, 6)]

# Dependency-safe load order. All models are historical models from the migration state.
MODEL_ORDER = [
    "SiteSettings",
    "ServiceCategory",
    "Governorate",
    "City",
    "MedicalSpecialty",
    "InsurancePartner",
    "ProviderType",
    "DownloadCategory",
    "Service",
    "Feature",
    "Statistic",
    "ProcessStep",
    "Testimonial",
    "FAQ",
    "Partner",
    "ManagementMember",
    "TPAService",
    "MedicalContact",
    "MedicalDownload",
    "NetworkProvider",
    "DownloadDocument",
]


def _upsert_row(Model, row, using):
    row = dict(row)
    pk = row.pop("id")
    valid_attnames = {field.attname for field in Model._meta.concrete_fields}
    defaults = {key: value for key, value in row.items() if key in valid_attnames}
    manager = Model.objects.using(using)
    obj = manager.filter(pk=pk).first()
    if obj is None:
        obj = Model(pk=pk)
    for key, value in defaults.items():
        setattr(obj, key, value)
    obj.save(using=using)
    return obj


def import_updated_content(apps, schema_editor):
    using = schema_editor.connection.alias
    payload = {"models": {}, "network_provider_m2m": {}}
    for data_file in DATA_FILES:
        with gzip.open(data_file, "rt", encoding="utf-8") as handle:
            shard = json.load(handle)
        payload["models"].update(shard.get("models", {}))
        payload["network_provider_m2m"].update(shard.get("network_provider_m2m", {}))
    models = payload["models"]

    for model_name in MODEL_ORDER:
        Model = apps.get_model("core", model_name)
        for row in models.get(model_name, []):
            _upsert_row(Model, row, using)

    NetworkProvider = apps.get_model("core", "NetworkProvider")
    for provider_id, relations in payload.get("network_provider_m2m", {}).items():
        provider = NetworkProvider.objects.using(using).filter(pk=int(provider_id)).first()
        if provider is None:
            continue
        provider.insurance_partners.set(relations.get("insurance_partners", []))
        provider.specialties.set(relations.get("specialties", []))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_remove_configurationversion_created_by_and_more"),
    ]

    operations = [
        migrations.RunPython(import_updated_content, migrations.RunPython.noop),
    ]
