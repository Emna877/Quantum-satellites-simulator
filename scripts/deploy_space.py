"""Publish the console to a Hugging Face Docker Space.

    pip install huggingface_hub
    hf auth login                      # paste a token with "Write" access
    python -m scripts.deploy_space --space <username>/quantum-satellites-simulator

Uploads a snapshot of the project files (the same files git would push, without history),
with deploy/huggingface/README.md as the Space's README. Files removed locally are removed
from the Space. The Space then builds the Dockerfile and starts the console.
"""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SPACE_README = ROOT / 'deploy' / 'huggingface' / 'README.md'
SKIP = ('README.md', 'docs/', 'deploy/')


def project_files():
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted(name for name in listed if (ROOT / name).is_file() and not name.startswith(SKIP))


def main():
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--space', required=True, help='<username>/<space-name>')
    args = parser.parse_args()

    api = HfApi()
    api.create_repo(args.space, repo_type='space', space_sdk='docker', exist_ok=True)
    files = project_files()
    operations = [CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(ROOT / name)) for name in files]
    operations.append(CommitOperationAdd(path_in_repo='README.md', path_or_fileobj=str(SPACE_README)))
    keep = set(files) | {'README.md', '.gitattributes'}
    operations += [CommitOperationDelete(path_in_repo=name)
                   for name in api.list_repo_files(args.space, repo_type='space') if name not in keep]
    api.create_commit(args.space, repo_type='space', operations=operations,
                      commit_message='Update the console from the project files')
    print(f'Uploaded {len(files) + 1} files. Build log and app: https://huggingface.co/spaces/{args.space}')


if __name__ == '__main__':
    main()
