from pathlib import Path
import jpype

# Paths
JVM_PATH = r"C:\Program Files\Java\jdk-25\bin\server\jvm.dll"
PROJECT_DIR = Path(r"C:\Users\Emna\Documents\QuantumSatellites").resolve()
DATA_DIR = PROJECT_DIR / "orekit-data"

# Start JVM and add Orekit/Hipparchus JARs
jars = [str(p) for p in PROJECT_DIR.rglob("*.jar")]
if not jpype.isJVMStarted():
    jpype.startJVM(JVM_PATH, "-ea", classpath=jars)

# Load Orekit data
JFile = jpype.JClass("java.io.File")
DataContext = jpype.JClass("org.orekit.data.DataContext")
DirectoryCrawler = jpype.JClass("org.orekit.data.DirectoryCrawler")

dm = DataContext.getDefault().getDataProvidersManager()
dm.addProvider(DirectoryCrawler(JFile(str(DATA_DIR))))

print("Orekit initialized and data loaded ✅")
