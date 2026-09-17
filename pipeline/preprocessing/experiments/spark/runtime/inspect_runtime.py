"""Print runtime evidence from the experiment image, without network access."""
import json
import platform
import subprocess

import pyspark


def command(*args):
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return (result.stdout + result.stderr).strip()


print(json.dumps({
    "python": platform.python_version(),
    "spark": pyspark.__version__,
    "java": command("java", "-version"),
    "node": command("node", "--version"),
    "node_modules": json.loads(command("node", "-e",
        "const p='/usr/local/lib/node_modules/npm/node_modules/';"
        "console.log(JSON.stringify(Object.fromEntries(['semver','npm-package-arg'].map(n=>"
        "[n,require(p+n+'/package.json').version]))))")),
    "python_packages": command("python3", "-m", "pip", "freeze").splitlines(),
}, indent=2))
