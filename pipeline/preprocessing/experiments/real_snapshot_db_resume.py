"""Resume the isolated experiment at DB loading with a separately pinned jar."""
import argparse
import hashlib
import json
from pathlib import Path

from pipeline.preprocessing.experiments.real_snapshot_run import Experiment
from pipeline.preprocessing.orchestration.runner import run_prefix
from pipeline.preprocessing.requirements_resolution.input import file_sha256


class DatabaseResume(Experiment):
    def __init__(self, root, jar, jar_sha256, baseline_sha256):
        super().__init__(root)
        self.jar = Path(jar).resolve()
        self.jar_sha256 = jar_sha256
        self.baseline_sha256 = baseline_sha256
        self.check_jar()

    def check_jar(self):
        if file_sha256(self.jar) != self.jar_sha256:
            raise ValueError('Pinned loader jar changed')

    def copy(self, label, rows):
        if label == 'baseline':
            print('REUSE_PUBLISHED_BASELINE: preprocessing will not repeat', flush=True)
            return
        return super().copy(label, rows)

    def preprocess(self, label, request):
        # Experiment.run configures the isolated helper before entering stages.
        import db_setup
        self.check_jar()
        db_setup.FROZEN_JAR = self.jar
        if label != 'baseline':
            return super().preprocess(label, request)
        prefix = run_prefix(request)
        with self.local.get_object(Bucket='pickage-curated', Key=prefix + '/run_manifest.json')['Body'] as stream:
            body = stream.read()
        with self.local.get_object(Bucket='pickage-curated', Key=prefix + '/_SUCCESS')['Body'] as stream:
            marker = json.loads(stream.read())
        bundle = json.loads(body)
        if (hashlib.sha256(body).hexdigest() != self.baseline_sha256
                or marker != {'manifest_sha256': self.baseline_sha256}
                or bundle.get('request') != request or bundle.get('status') != 'COMPLETE'):
            raise ValueError('Completed baseline identity changed')
        print('DB_RESUME: published baseline confirmed; loader will verify all referenced files', flush=True)
        return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'jar', 'jar-sha256', 'baseline-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    import msvcrt
    with (Path(args.root) / 'experiment.lock').open('a+b') as handle:
        handle.seek(0)
        if not handle.read(1):
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        DatabaseResume(args.root, args.jar, args.jar_sha256, args.baseline_sha256).run()


if __name__ == '__main__':
    main()
