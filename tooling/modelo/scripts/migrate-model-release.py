"""Print a non-accepting identity migration draft; never modify input files."""

import argparse
from pathlib import Path, PurePosixPath

import yaml
from modelo.identity import migrate_bound_model, migrate_offering
from modelo.loader import load_yaml_mapping

parser = argparse.ArgumentParser(description=__doc__)
subject = parser.add_mutually_exclusive_group(required=True)
subject.add_argument("--model", type=Path)
subject.add_argument("--offering", type=Path)
parser.add_argument("--evidence", type=Path)
parser.add_argument("--id-pointer")
parser.add_argument("--reviewed-model-id")
args = parser.parse_args()


def read(path: Path):
    absolute = path.absolute()
    return load_yaml_mapping(absolute.parent, PurePosixPath(absolute.name))


if args.model:
    if not all((args.evidence, args.id_pointer, args.reviewed_model_id)):
        parser.error("model migration requires --evidence, --id-pointer and --reviewed-model-id")
    draft = migrate_bound_model(
        read(args.model),
        read(args.evidence),
        id_pointer=args.id_pointer,
        reviewed_model_id=args.reviewed_model_id,
    )
else:
    if any((args.evidence, args.id_pointer, args.reviewed_model_id)):
        parser.error("offering migration takes only --offering")
    draft = migrate_offering(read(args.offering))
print(yaml.safe_dump(draft, sort_keys=True), end="")
