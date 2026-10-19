# Rigol Transient Analyzer

A C17 application with a local browser interface and command-line tools
for measuring how a DC supply responds to sudden load changes. It controls
listed Rigol DHO800 and DHO900 models over Ethernet, downloads voltage and
current waveforms from the same acquisition, and calculates the response
to each load transition.

A function generator drives a MOSFET switched load. CH1 measures supply
voltage at the circuit; CH2 measures a current-sense resistor. The program
converts the resistor voltage into current, detects load steps, and saves
measurements, summaries, statistics, and optional plots.

**Windows: [Download the installer](https://github.com/IcaroRamosDM/rigol-transient-analyzer/releases/latest).**

## Features

- Local browser interface in Portuguese and English for setup, measurements, plots, and history.
- Named bench profiles, read-only signal checks, and device-bound setup backup/restore.
- Comparison of up to four saved records aligned at load transitions.
- Saved-capture reanalysis preserving original samples and recording provenance.
- Bilingual PDF reports with vector plots, analysis criteria, and observations.
- Automatic model detection or manual selection, checked against instrument identity.
- Model-specific timebase and vertical-scale limits from a shared profile catalog.
- Scope configuration with readback, continuous visualization, and RUN/STOP controls.
- Fresh single acquisitions, with both channels read from one frozen record.
- Up to 1,000,000 samples per channel, transferred in 16-bit WORD format.
- Current conversion using a configurable sense resistance.
- Rising and falling load-step detection with hysteresis.
- Before/after averages, voltage and current changes, voltage sag,
  overshoot, and settling time within a configurable observation window.
- Repeated captures with statistics grouped by transition direction.
- CSV and JSON export, plus overview and event-detail PNG plots.
- Offline simulation and reanalysis of saved samples.

Acquisition and analysis run in C. Python serves the local interface;
Matplotlib generates optional PNG plots. The interface and PDF reports support Portuguese and English. Command options,
raw core logs, exported field names, and legacy PNG labels retain Portuguese;
this guide explains their meaning.

## Instrument compatibility

The current profiles use the common DHO800/DHO900 command set:

| Model | Analog channels | Bandwidth | Hardware validation |
| --- | --- | --- | --- |
| DHO802 | 2 | 70 MHz | Bench acquisition validated |
| DHO804 | 4 | 70 MHz | Pending |
| DHO812 | 2 | 100 MHz | Pending |
| DHO814 | 4 | 100 MHz | Pending |
| DHO914 | 4 | 125 MHz | Pending |
| DHO914S | 4 | 125 MHz | Pending |
| DHO924 | 4 | 250 MHz | Pending |
| DHO924S | 4 | 250 MHz | Pending |

The DHO802 was tested on the reference bench with firmware `00.01.05`.
The other profiles are prepared from Rigol documentation and checked with
a protocol simulator. These software checks do not establish operation on
the corresponding physical instruments. Their interface labels explicitly
show that bench validation is pending.

The analyzer uses **CH1 for supply voltage and CH2 for sense voltage** on
all listed models, with a maximum of **1,000,000 samples per channel**.
These are application limits, including on four-channel instruments.

| Profile family | Time per division | Vertical scale at 1x |
| --- | --- | --- |
| DHO800 models listed above | 5 ns to 500 s | 500 microvolts/div to 10 V/div |
| DHO900 models listed above | 2 ns to 500 s | 200 microvolts/div to 10 V/div |

Displayed vertical-scale limits are multiplied by the selected probe
factor. For example, the DHO802 minimum is 5 mV/div with a 10x probe.

**Detectar automaticamente (detect automatically)** is the default in the
interface; the command-line equivalent is `--modelo auto`. Manual selection
requires the connected instrument to report that exact model. The
acquisition executable and interface recheck identity before control
commands, so a mismatched or unlisted model is rejected before applying
adjustments.

Only the exact models in the table have profiles. Other Rigol families
require a separate review of commands, waveform framing and scaling, and
trigger behavior before a driver can be added. Model capabilities are
defined once in `include/rigol_models.def` and shared by C and Python.

## Windows installer

Download the Windows x64 installer from [GitHub Releases](https://github.com/IcaroRamosDM/rigol-transient-analyzer/releases/latest).
The file is named `RigolTransientAnalyzer-<version>-windows-x64-setup.exe`.

1. Run the installer and follow the installation wizard. Installation is
   for the current user and does not require administrator privileges.
2. Open **Rigol Transient Analyzer** from the Windows Start menu. The
   application opens its interface in the default browser.
3. Click **Explorar demonstração** to try it without instruments, or follow
   the measurement and scope-configuration instructions below.

The installer includes the native C executable, Python runtime, plotting
libraries, and interface assets. Users do not need WSL, Python, a compiler,
or an Internet connection to run the installed application. Ethernet
communication with the scope remains necessary for real measurements.

The package targets **Windows 10 version 1903 or later and Windows 11,
x64**. The interface stays local to the computer. If its usual port 8765
is occupied, the Windows app tries ports 8766 through 8775. Launching it
again opens the existing instance.

| Location | Contents |
| --- | --- |
| `%LOCALAPPDATA%\Programs\RigolTransientAnalyzer` | Default application installation |
| Windows Documents folder → `Rigol Transient Analyzer\resultados` | Measurements, CSV/JSON exports, and PNGs |
| `%LOCALAPPDATA%\RigolTransientAnalyzer` | Named profiles, setup backups, instance state, caches, and `logs\application.log` |

The actual Windows Documents location is used, including redirected
folders. The Start-menu **Resultados** shortcut opens the measurements
folder. Use **Encerrar aplicativo** in the interface to stop the background
application; closing the browser alone leaves it available for reopening.

Profiles are stored in the application-data profiles/ directory; full setup
backups are in backups/. Source installations use build/ for this data by default.
Keep setup files together with their metadata and firmware information.

Run a newer installer to update the application. Finish or cancel an
active measurement first: the installer waits for executable files to be released and refuses to update or uninstall
while a measurement or scope-control operation is active. Uninstall from
Windows Settings → Apps → Installed apps. Saved measurements, profiles, backups and per-user
application data are preserved.

If the installer still reports files in use after finishing/cancelling the
measurement and closing the application, open Windows Task Manager → Details,
end leftover RigolTransientAnalyzer.exe entries and retry. This can recover a
stalled browser-launch process from an older version.

The current installer is not digitally signed. A `SHA256SUMS.txt` file is
provided with the release. To calculate a downloaded installer's checksum
in PowerShell, replace the filename with the version you downloaded:

```powershell
Get-FileHash .\RigolTransientAnalyzer-0.2.0-windows-x64-setup.exe -Algorithm SHA256
```

Compare the value with the release checksum file. Physical model-validation
status remains as documented in the compatibility table above.

## Build from source on Linux or WSL

Requirements are a C17 compiler, GNU Make, and Python 3.11 or newer with virtual
environment support for integration tests and optional plots.

On Ubuntu:

```bash
sudo apt update
sudo apt install git build-essential python3 python3-venv
```

Clone the repository and build it:

```bash
git clone https://github.com/IcaroRamosDM/rigol-transient-analyzer.git
cd rigol-transient-analyzer
make
make dependencias
```

The executable is `build/carac_transientes`. `make dependencias` installs
plotting dependencies from `requirements-graficos.txt` into `.venv`.
These dependencies are needed for PNG generation; the browser interface,
interactive charts, and CSV/JSON exports use Python's standard library
and local browser assets.

Verify the software without connecting any instruments:

```bash
make test
make sanitize
./build/carac_transientes --simular --graficos
```

Simulation generates synthetic data and does not communicate with the
oscilloscope. A successful run prints `Ensaio concluido` and the path to
a new results directory.

## Local browser interface

For an installed Windows copy, use the Start-menu shortcut. To start a
source checkout on Linux or WSL, run this from the project directory:

```bash
make interface
```

It opens `http://localhost:8765` in the browser. On Windows, with Ubuntu
under WSL installed, developers can also double-click `iniciar-interface.cmd`
from the source checkout. This launcher uses WSL; the Windows installer
provides the native application described above. The Windows launcher defaults to the
`Ubuntu-26.04` distribution; another installed distribution can be selected
with `iniciar-interface.cmd -Distribution NAME`. On Linux, `./iniciar-interface.sh` builds the
executable and starts the interface.

Use **Idioma / Language** to switch between Portuguese and English.
The choice is saved in this browser. Switching reloads the page and is
disabled during active operations. The interface has five work areas:

1. **Medição (measurement):** select **Modelo do Rigol** or leave
   **Detectar automaticamente**, enter the scope IP, and click **Conectar**.
   Check the identified model, match the probe factors to their physical
   switches, and set the sense resistance and capture count. Use the
   **Rigol** tab to review the acquisition profile, then click
   **Iniciar medição real** on the measurement tab.
2. **Rigol (instrument control):** read current settings, edit the bench
   profile, apply and confirm it, resume continuous visualization, or
   freeze the scope display.
3. **Preparação (setup):** consult the circuit diagram, probe connections,
   supply settings, and generator settings.
4. **Histórico (history):** open saved runs, select captures and transitions,
   and download samples, event metrics, configuration, statistics, and
   available PNG images.
5. **Comparar (compare):** overlay two to four saved records aligned at a
   selected load transition and compare their metrics.

### Configure the scope from the interface

After connecting on the **Medição** tab:

1. Open **Rigol**. The **Modelo do Rigol** selector mirrors the selection
   on the measurement tab. Check the model and validation status shown.
2. Click **Ler ajustes (read settings)** to display the instrument's current
   settings and their read time. This reading leaves the form values intact.
3. Set **Ponta CH1** and **Ponta CH2** to match the physical probe switches.
   Set **Pontos por canal**, **Tensão nominal (V)**, both channel scales,
   **Tempo por divisão**, and **Limite de banda**.
4. Check the summary below the form: CH1 is centered on the nominal supply
   voltage, CH2 on 0 V, both use DC coupling, and the trigger is the CH2
   rising edge at the midpoint of the two current thresholds.
5. Click **Aplicar e visualizar (apply and visualize)**. The program applies
   the profile, checks the instrument readback, and starts continuous
   acquisition with automatic trigger sweep. Expect a success message and
   the confirmed settings under **Configuração confirmada**.
6. Use **Congelar (freeze)** for STOP or **Retomar visualização (resume
   visualization)** to resume automatic continuous acquisition. To save
   measurements, return to **Medição** and click **Iniciar medição real**.

**Usar perfil de 5 V** loads the reference defaults into the form; click
**Aplicar e visualizar** to send them to the instrument. Applying a profile
does not save a measurement. A real measurement applies the form's profile,
takes fresh single acquisitions, exports the data, and finishes in STOP.

### Timebase units and steps

For **Tempo por divisão**, select **ns**, **µs**, **ms**, or **s** next to the
value. Changing units preserves the time setting. Use **− / +** or the
keyboard arrow keys to move between values on the profile's timebase grid.

The increment changes with the range. For example, 205 µs advances to
210 µs. A typed 206 µs is adjusted to 205 µs when the field loses focus or
Enter is pressed, with a message showing the adjustment. The server also
rejects values outside the selected grid, and applying a profile confirms
the actual timebase by reading it back from the scope. Additional profiles
still require hardware validation as stated above.

With automatic detection, connect first so the controls use the detected
model's limits. Model selection, form settings, and the preferred time
unit are remembered by the browser. Recheck the physical probe switches
when reopening the application.

### Measure, inspect, and export

Use **Explorar demonstração** to try the complete workflow without an
instrument. This mode produces a clearly labeled synthetic 10,000-sample
record per capture. It never contacts the Rigol. Real measurements retain
the selected memory depth, initially 1,000,000 samples per channel.

The voltage and current charts share the time axis. Drag across a chart
or use the zoom buttons to inspect a smaller interval. Select a transition
for its metrics, choose **Janela do evento** for the analysis window, or
**Borda ±5 µs** for the switching detail. Plot reduction preserves extrema
from both channels; C calculates metrics from the complete record.

Progress distinguishes configuration, waiting for a trigger, waveform
transfer, analysis, and file export. **Cancelar ensaio** requests graceful
cancellation; for real acquisition, the application also attempts to
confirm STOP on the scope. The supply and generator remain manually
controlled. **Encerrar aplicativo** stops the local interface after the
current operation has finished or been cancelled.

The interface binds only to the local loopback address. It uses Python's
standard library and local HTML, CSS, and JavaScript assets. Acquisition
and analysis still run in the same C executable. PNG export uses the
existing optional Matplotlib dependencies.

To run without automatically opening a browser, or to select another
local port (close an already running instance first):

```bash
make interface UI_ARGS="--no-browser --port 8766"
```

### Named bench profiles

In **Rigol → Perfis salvos (saved profiles)**, enter a profile name and click
**Salvar como novo (save as new)**. Profiles include the instrument address/model,
probe factors, acquisition settings, sense resistance and analysis criteria.
Select an existing profile to load, update or remove it. Up to 100 uniquely
named profiles are supported. When automatic detection identifies a connected
instrument at that address, the saved profile records its concrete model and limits.

**Carregar no formulário (load into form)** only fills the controls.
Review the physical probe switches, then use **Aplicar e visualizar** to send
the acquisition settings. Supply and generator adjustments remain manual.
Removed profiles retain a recovery copy in application data.

### Read-only signal checks

After connecting, click **Verificar sinais antes de medir (check signals before
measuring)**. The check reads current settings and measurements to check channel
visibility, configured probe factors, DC coupling, vertical range, load-step
levels, frequency, duty cycle and analysis-window duration.

Unavailable readings remain inconclusive. A frozen record is explicitly
flagged: its readings describe that record, not a fresh acquisition.
The check does not change settings or trigger a capture. It cannot read the
physical 1x/10x switches or certify correct wiring.

### Setup backup and restore

In **Rigol → Backup dos ajustes do Rigol (Rigol settings backup)**, click
**Guardar ajustes atuais (back up current settings)**. The full system setup
is transferred to this computer with its SHA-256 checksum, model, serial number,
firmware and a settings readback.

To preserve settings before a real measurement, enable **Criar backup do Rigol
antes da medição real (back up Rigol settings before real measurement)**.
Acquisition starts only after that backup succeeds. This option is off by
default; demo and file reanalysis never contact the instrument.

To restore, connect the same instrument, select its backup and click
**Restaurar backup selecionado (restore selected backup)**. A damaged file or
a different model, serial number or firmware is rejected. The application
creates a recovery backup first, sends the saved setup, then verifies CH1/CH2,
timebase, memory and edge-trigger settings by readback. The transferred setup
contains settings beyond those explicitly verified fields.

Restoration is an explicit action; finishing a measurement does not automatically
restore settings. If readback fails, the recovery copy and its identifier remain
available. This flow was physically validated on the reference DHO802 firmware
00.01.05; other models remain pending physical validation.

### Compare saved runs

Open **Comparar (compare)** or **Comparar com outro ensaio (compare with another
run)**. Choose two to four runs, a capture and a valid transition for each,
then click **Comparar registros (compare records)**. Directions must match.

Plots share a time axis centered at each load step. The table shows current
change, sag, overshoot and settling time; parentheses show differences from
the first record. Missing settling times remain unavailable. Different analysis
criteria produce a visible warning. Metrics use the complete records; plots
use extrema-preserving reduction.

### Reanalyze a capture

Expand **Reanalisar esta captura (reanalyze this capture)** below a result.
Adjust thresholds, average window, guard, horizon, tolerance or hold time,
then click **Criar nova análise (create new analysis)**.

The C analyzer reads the saved samples into a new run labeled **Reanálise de
arquivo (file reanalysis)**. It neither contacts the scope nor changes the
original files. Existing current conversion and sense resistance are preserved.
A `proveniencia.json` record identifies the source run, capture, original
timestamp/origin and sample SHA-256. Use **Abrir registro original (open original
record)** to return to that source.

### PDF reports

Expand **Gerar relatório PDF (generate PDF report)**. Enter optional observations
(up to 4,000 characters), click **Gerar PDF (generate PDF)** and then **Baixar
relatório (download report)**.

The selected interface language is used for the report. It includes data origin,
instrument, timestamp, sense resistance, sample count, analysis criteria,
voltage/current vector plots and event metrics. Simulations and reanalyses
are explicitly labeled. Tables and long notes are paginated. For bounded output
size, the table shows the first 200 events; the complete list remains in CSV.
Each export creates a separate PDF under the run's `reports/` directory.

The PDF runtime is bundled in the Windows installer. Source users install
dependencies with `make dependencias` and start the server using
`.venv/bin/python interface/servidor.py`.

## Reference bench setup

The physical setup used to validate acquisition consists of:

- Rigol DHO802 oscilloscope, connected to the computer by Ethernet.
- Hantek HDP135V6S supply, set to **5.00 V** with a **0.350 A** current limit.
- ICEL Manaus GV-2002 function generator.
- IRFZ44N N-channel MOSFET and the resistors below.
- Two probes and a BNC-to-alligator cable for the generator.

Disable supply and generator outputs before wiring. All references to
**0 V** mean the same circuit return node at the bottom of the 1 ohm
sense resistor.

| Component or lead | Connection |
| --- | --- |
| Supply positive | Circuit +5 V node |
| Supply negative | Circuit 0 V node |
| 100 ohm / 1 W resistor | Between +5 V and 0 V; permanent load |
| 22 ohm / 5 W resistor | Between +5 V and MOSFET drain (D) |
| 1 ohm / 1 W sense resistor | Between MOSFET source (S) and 0 V |
| 220 ohm / 0.25 W resistor | Between generator OUT red lead and gate (G) |
| 100 kilohm / 0.25 W resistor | Between gate (G) and source (S) |
| Generator OUT black lead | Circuit 0 V node |

Set the generator to a **1 kHz square wave**, approximately **50% duty
cycle**, with an actual unloaded output near **-10 V to +10 V**. On the
GV-2002 unit used here, **WAVE 2** selects the square wave. Check the actual
output on the oscilloscope before connecting it to the gate; the amplitude
display can differ from the voltage measured into a high-impedance input.
Reapply the generator settings after power cycling.

The IRFZ44N gate-to-source absolute maximum rating is **+/-20 V**.
Keep the drive comfortably within that limit, including overshoot.
See the [Infineon IRFZ44N datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-irfz44n-datasheet-en.pdf)
for the ratings and pinout.

### Probe connections

| Channel | Physical probe switch | Probe tip | Ground clip |
| --- | --- | --- | --- |
| CH1: supply voltage | **10x** | +5 V at the load input | Circuit 0 V |
| CH2: sense voltage | **1x** | MOSFET source / top of 1 ohm resistor | Circuit 0 V |

Both probe ground clips and the generator black lead connect to the
same **0 V** node. Keep the probe ground paths short.

With outputs enabled, expect CH1 near 5 V and CH2 alternating between
approximately 0 V and 0.21 V. The program calculates current as:

```text
I = V_CH2 / R_sense
0.21 V / 1 ohm = 0.21 A
```

Reported current belongs to the **switched branch only**. The permanent
100 ohm branch adds about 50 mA to the total supply current. The supply
therefore sees approximately 50 mA with the MOSFET off and 260 mA with it on.

## Capture real measurements

Confirm that the computer can reach the scope. The reference bench
uses IP address `169.254.112.67` and raw TCP port `5555`. Replace the IP
address in the examples if your instrument uses a different one.

List the available model profiles without contacting an instrument:

```bash
./build/carac_transientes --listar-modelos
```

Capture once with automatic model detection and the reference probe settings:

```bash
./build/carac_transientes --sonda-v 10 --sonda-i 1 --graficos 169.254.112.67
```

To require the reference DHO802 explicitly:

```bash
./build/carac_transientes --modelo DHO802 --sonda-v 10 --sonda-i 1 --graficos 169.254.112.67
```

For a DHO914, use `--modelo DHO914` and that instrument's IP address.
Selecting DHO914 while connecting to a DHO802 produces a model-mismatch
error before scope adjustments are sent.

Capture three new records and combine their event statistics:

```bash
./build/carac_transientes --sonda-v 10 --sonda-i 1 --capturas 3 --graficos 169.254.112.67
```

**Probe factors must match the physical switches.** Command-line defaults
are 1x for both probes, so reference CH1 requires `--sonda-v 10`. The browser
interface initially uses 10x for CH1 and 1x for CH2.

The program applies this acquisition profile:

| Setting | Reference profile |
| --- | --- |
| CH1 | DC coupling, 0.5 V/div, centered on 5 V |
| CH2 | DC coupling, 0.1 V/div, centered on 0 V |
| Timebase | 200 microseconds/div |
| Bandwidth limit | 20 MHz on both channels |
| Acquisition | Normal, 1,000,000 points per channel |
| Trigger | CH2 rising edge at 0.1 V |
| Trigger/network timeout | 5 seconds |

The program confirms acquisition has started, requests a single trigger,
waits for completion, and downloads both channels while the record is
frozen. Each repetition requests another fresh acquisition. The scope
remains in **STOP** after the run. The supply and generator remain
manually operated.

To resume continuous acquisition from the terminal:

```bash
make antigos
./build/consultar_rigol 169.254.112.67 ':TRIG:SWE AUTO;:RUN;*OPC;*OPC?'
```

The reply `1` acknowledges command completion. The compound `*OPC;*OPC?`
sequence was verified on the reference DHO802 firmware.

### Apply a profile without acquiring data

Apply and confirm the reference profile without creating a results directory:

```bash
./build/carac_transientes --configurar-apenas --modelo DHO802 --sonda-v 10 --sonda-i 1 169.254.112.67
```

This command leaves the scope in STOP. The interface's **Aplicar e visualizar**
action uses the same C configuration mode, then resumes continuous acquisition.

The CLI accepts `--tempo-div` in **seconds**, for example
`--tempo-div 0.000210` for 210 µs/div. Use a value on the selected model's
grid; a setting quantized to a different value by the scope fails readback
confirmation. The browser provides the unit selector and step controls.

### Other operating modes

Request a fresh capture while retaining current scope settings:

```bash
./build/carac_transientes --sem-configurar --graficos 169.254.112.67
```

Stop acquisition and read current memory without applying the profile:

```bash
./build/carac_transientes --existente --graficos 169.254.112.67
```

For these modes, confirm probe factors on the scope itself. If memory
depth differs from 1,000,000 points, pass the matching `--pontos` value.
Supported values are `1000`, `10000`, `100000`, and `1000000`.

Reanalyze saved samples without connecting to an instrument. Replace
`resultados/your_run` with the directory printed by a previous run:

```bash
./build/carac_transientes --entrada resultados/your_run/captura_001/amostras.csv --graficos
```

`--existente` and `--entrada` accept one record rather than presenting
the same data as multiple fresh captures. Metadata distinguishes
`CAPTURA_NOVA` (new acquisition), `MEMORIA_EXISTENTE` (existing memory),
`SIMULACAO` (simulation), and `ARQUIVO` (file reanalysis).

For every option and default:

```bash
./build/carac_transientes --help
```

## Measurement criteria

A rising event is detected when switched current reaches **0.15 A**;
a falling event is detected when it reaches **0.05 A** or below.
These two thresholds provide hysteresis so fluctuations between them
do not repeatedly change the detected state.

Default windows are relative to the detected edge:

| Parameter | Default |
| --- | --- |
| Before-step average | -70 to -20 microseconds |
| Final average | +250 to +300 microseconds |
| Observation horizon | 300 microseconds |
| Settling tolerance | +/-0.05 V around the final voltage average |
| Minimum remaining observation inside tolerance | 20 microseconds |

- **Voltage/current change:** final average minus before-step average.
- **Sag:** final voltage average minus the minimum after the edge,
  limited to nonnegative values.
- **Overshoot:** maximum after the edge minus the final voltage average,
  limited to nonnegative values.
- **Settling time:** earliest sample after the edge from which all
  remaining samples through the horizon stay inside the tolerance band,
  with at least the minimum observation duration left.

Incomplete windows and windows containing another detected edge are
flagged and excluded from event metrics. An edge near the end of a record
may therefore be detected but not analyzable. An otherwise valid event
can also fail to settle within the selected horizon.

Use `--resistor` for sense resistance in ohms, `--baixo-a` and `--alto-a`
for current thresholds, and `--tolerancia-v` for absolute voltage tolerance.
Window controls are `--janela-us`, `--guarda-us`, `--horizonte-us`, and
`--permanencia-us`, in microseconds.

Measurements include supply, wiring, contacts, switched load, and probe
effects. Peaks and settling times describe this complete setup; they do
not certify the supply's intrinsic performance.

## Output files

Each run creates a new directory under `resultados/` and prints its
absolute path. Use `--saida PATH` to select another **new** directory;
existing output directories are refused.

```text
resultados/ensaio_.../
  execucao.json
  estatisticas.csv
  captura_001/
    amostras.csv
    eventos.csv
    metadados.json
    resumo.txt
    graficos/
      visao_geral.png
      evento_001_...
      graficos.json
  captura_002/
    ...
```

| File | Contents |
| --- | --- |
| `amostras.csv` | `tempo_s,tensao_v,corrente_a`: seconds, volts, amperes |
| `eventos.csv` | Direction, validity, averages, changes, extrema, and settling per event |
| `metadados.json` | Data origin, instrument identity, timestamp, configuration, and waveform scaling |
| `resumo.txt` | Human-readable capture summary |
| `estatisticas.csv` | Counts, means, sample standard deviations, minima, and maxima by direction |
| `execucao.json` | Completed data export and run totals |
| `proveniencia.json` | Source metadata and sample checksum for interface reanalyses |
| `reports/` | Individually exported bilingual PDF reports |
| `graficos/` | Overview and event-detail PNGs, plus a plot manifest |

In exported directions, `subida` means rising current and `descida` means
falling current. Sample standard deviation is empty when fewer than two
observations are available.

Calculations use the full sample record. Plot downsampling preserves
voltage and current extrema for display. Plots are saved to disk rather
than opened automatically; open `graficos/visao_geral.png` to view a run.

To generate plots later from saved results:

```bash
make graficos ENSAIO=resultados/your_run
```

Exit status is `0` for a completed run with valid events, `2` when data
was exported but no transition has complete analysis windows, and `1`
for an error. If plotting fails, previously exported data is retained.

Results, compiled binaries, and `.venv` are excluded from Git.

## Validation and source layout

Software checks cover event detection, known analytical settling behavior,
incomplete windows, late disturbances, invalid data, fragmented network
transfers, trigger sequencing, export, reanalysis, and plots. Interface
checks cover configuration readback, exclusive operations, cancellation,
history, downloads, and local-access restrictions. Model checks exercise
every catalog entry's configuration, DHO914 waveform acquisition, model
limits, and rejection of unknown, mismatched, or swapped instruments
before control commands are sent.

Run `make test` for C analysis and Python unit/integration checks, and
`make sanitize` for the same checks with AddressSanitizer and
UndefinedBehaviorSanitizer. Protocol fixtures use local simulated
instruments. Workflow tests cover profile persistence, diagnostics, backup
integrity/identity and restore readback, operation exclusion, immutable reanalysis,
aligned comparisons, bilingual PDFs, translation coverage and HTTP request guards.
JavaScript syntax checks run when Node.js is available; set NODE to its executable
path when it is not in PATH. The JavaScript timebase contract is in
`testes/test_timebase.mjs`; it is a separate check and is not run by
`make test`.

Physical acquisition was validated with a Rigol DHO802 running firmware
`00.01.05`, including fresh records with 1,000,000 samples per channel.
The sample interval is read from the waveform preamble and can vary with
acquisition settings. The other model profiles remain pending physical
validation. Software tests and physical acquisition establish tool
operation separately from electrical interpretation of the waveforms.

| Path | Purpose |
| --- | --- |
| `src/main.c` | Options and run coordination |
| `src/rigol.c` | Network, scope configuration, triggering, waveform transfer |
| `src/modelos.c` | Model identity parsing and C compatibility checks |
| `VERSION` | Application and installer version |
| `include/rigol_models.def` | Shared model catalog and capability limits |
| `src/analise.c` | Event detection, measurements, synthetic waveforms |
| `src/arquivos.c` | Export, CSV import, statistics, plot invocation |
| `src/comum.c`, `include/carac.h` | Shared types and utilities |
| `interface/servidor.py` | Local server entry point and single-instance lifecycle |
| `interface/rta/runtime.py`, `instance.py`, `process.py` | Platform paths, instance lock, and cancellation |
| `packaging/windows/` | Native launcher, dependency pins, manifests, installer builder, and smoke tests |
| `interface/rta/` | Settings, model profiles, scope control, jobs, results, and HTTP API |
| `interface/rta/profiles.py`, `backups.py`, `diagnostics.py` | Profiles and instrument checks/setup protection |
| `interface/rta/comparison.py`, `reports.py`, `workbench.py` | Comparisons, PDFs and workflow coordination |
| `interface/static/modules/workbench.js`, `i18n.js` | Workbench panels and presentation translations |
| `interface/static/modules/` | Browser modules for controls, models, timebase, charts, and results |
| `interface/static/assets/circuit.svg` | Reference circuit diagram |
| `interface/iniciar-windows.ps1` | Windows-to-WSL launcher |
| `ferramentas/graficos.py` | Saved-record plotting |
| `testes/` | Analysis and integration tests |
| `Makefile` | Build, test, plotting dependency, and utility targets |

The original utility programs remain available through `make antigos`:
`identificar_rigol`, `consultar_rigol`, `parametros_onda`, and `receber_onda`,
all built under `build/`.

### Build the Windows installer

These tools are needed only on the development/build computer:
64-bit CPython 3.14, MinGW-w64 GCC with `windres`, and NSIS 3.
The builder detects GCC in PATH or the standard MSYS2 UCRT64/MINGW64
locations, and NSIS in PATH or its standard installation directory.

From a source checkout in Windows PowerShell:

```powershell
py -3.14 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install -r packaging\windows\requirements-build.txt
.\.venv-windows\Scripts\python.exe packaging\windows\build.py
```

The builder compiles the native core, freezes the application and plotting
runtime, generates version resources and third-party notices, exercises a
Unicode-path simulation with PNG and PDF export, and creates the installer and
checksums under `dist\windows`. Build dependencies are pinned separately
from the runtime requirements used by source installations.

A prebuilt Windows x64 core may be supplied with `--core PATH`.
`--output PATH` selects the build destination; `--skip-installer` creates
and verifies the application folder without invoking NSIS. On Linux/WSL,
`make windows-core` can cross-compile the C executable with MinGW-w64;
the bundled Python application must be built on Windows.

`packaging/windows/smoke.py` verifies an actual installation with Python
and WSL absent from the application's PATH, demonstration PNGs and
downloads, profiles, comparison, reanalysis, bilingual PDFs, backup/restore, diagnostics,
single-instance behavior, cancellation, refusal of updates
during acquisition, and preservation of results on upgrade/uninstall.
Run it on a Windows account without an existing installed copy, using a
new empty test directory:

```powershell
.\.venv-windows\Scripts\python.exe packaging\windows\smoke.py --installer dist\windows\RigolTransientAnalyzer-0.2.0-windows-x64-setup.exe --work dist\windows\smoke-test
```

Instrument references:

- [Rigol DHO800/DHO900 Programming Guide](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf)
- [Rigol DHO800 Data Sheet](https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DHO800_DataSheet_EN.pdf)
- [Rigol DHO900 Data Sheet](https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DHO900_DataSheet.pdf)
- [PyInstaller documentation](https://pyinstaller.org/en/stable/)
- [NSIS documentation](https://nsis.sourceforge.io/Docs/)

## Author

**Icaro Ramos Rodrigues dos Santos**

Electronics Engineer | Software Engineer | Embedded Systems | Firmware | C | C++ | Assembly | RISC-V | ARM Cortex-M | STM32 | Linux | Hardware Design | Verilog | Design Verification | UVM

- **GitHub:** [github.com/IcaroRamosDM](https://github.com/IcaroRamosDM)
- **LinkedIn:** [linkedin.com/in/icaro-ramos-r](https://www.linkedin.com/in/icaro-ramos-r/)
- **Email:** [icaroelt@gmail.com](mailto:icaroelt@gmail.com)
