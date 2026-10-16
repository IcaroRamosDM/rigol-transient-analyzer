# Rigol Transient Analyzer

A C17 command-line tool for measuring how a DC supply responds to sudden
load changes. It controls a Rigol DHO802 over Ethernet, downloads voltage
and current waveforms from the same acquisition, and calculates the
response to each load transition.

A function generator drives a MOSFET switched load. CH1 measures supply
voltage at the circuit; CH2 measures a current-sense resistor. The program
converts the resistor voltage into current, detects load steps, and saves
measurements, summaries, statistics, and optional plots.

## Features

- Fresh single acquisitions, with both channels read from one frozen record.
- Up to 1,000,000 samples per channel, transferred in 16-bit WORD format.
- Current conversion using a configurable sense resistance.
- Rising and falling load-step detection with hysteresis.
- Before/after averages, voltage and current changes, voltage sag,
  overshoot, and settling time within a configurable observation window.
- Repeated captures with statistics grouped by transition direction.
- CSV and JSON export, plus overview and event-detail PNG plots.
- Offline simulation and reanalysis of saved samples.

Acquisition and analysis run in C. Python and Matplotlib generate plots.
Options, console messages, and exported field names retain their original
Portuguese names; this guide explains their meaning.

## Requirements and build

Run on Linux, or in Ubuntu under Windows Subsystem for Linux (WSL).
Requirements are a C17 compiler, GNU Make, and Python 3 with virtual
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

The executable is `build/carac_transientes`. The second command installs
plotting dependencies from `requirements-graficos.txt` into `.venv`.

Verify the software without connecting any instruments:

```bash
make test
make sanitize
./build/carac_transientes --simular --graficos
```

Simulation generates synthetic data and does not communicate with the
oscilloscope. A successful run prints `Ensaio concluido` and the path to
a new results directory.

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

Capture once with the reference probe settings:

```bash
./build/carac_transientes --sonda-v 10 --sonda-i 1 --graficos 169.254.112.67
```

Capture three new records and combine their event statistics:

```bash
./build/carac_transientes --sonda-v 10 --sonda-i 1 --capturas 3 --graficos 169.254.112.67
```

**Probe factors must match the physical switches.** The defaults are
1x for both probes, so reference CH1 requires `--sonda-v 10`.

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
./build/consultar_rigol 169.254.112.67 ':TRIG:SWE NORM;:RUN;*OPC;*OPC?'
```

The reply `1` acknowledges command completion. The compound `*OPC;*OPC?`
sequence was verified on the reference DHO802 firmware.

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
transfers, trigger sequencing, export, reanalysis, and plots. Run
`make test` for unit and integration checks, and `make sanitize` for the
same checks with AddressSanitizer and UndefinedBehaviorSanitizer.

Physical acquisition was validated with a Rigol DHO802 running firmware
`00.01.05`, including records with 1,000,000 samples per channel and a
3.2 ns sample interval. Software tests and physical acquisition establish
tool operation separately from electrical interpretation of the waveforms.

| Path | Purpose |
| --- | --- |
| `src/main.c` | Options and run coordination |
| `src/rigol.c` | Network, scope configuration, triggering, waveform transfer |
| `src/analise.c` | Event detection, measurements, synthetic waveforms |
| `src/arquivos.c` | Export, CSV import, statistics, plot invocation |
| `src/comum.c`, `include/carac.h` | Shared types and utilities |
| `ferramentas/graficos.py` | Saved-record plotting |
| `testes/` | Analysis and integration tests |
| `Makefile` | Build, test, plotting dependency, and utility targets |

The original utility programs remain available through `make antigos`:
`identificar_rigol`, `consultar_rigol`, `parametros_onda`, and `receber_onda`,
all built under `build/`.

Instrument command reference:
[Rigol DHO800/DHO900 Programming Guide](https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf).

## Author

**Icaro Ramos Rodrigues dos Santos**

Electronics Engineer | Software Engineer | Embedded Systems | Firmware | C | C++ | Assembly | RISC-V | ARM Cortex-M | STM32 | Linux | Hardware Design | Verilog | Design Verification | UVM

- **GitHub:** [github.com/IcaroRamosDM](https://github.com/IcaroRamosDM)
- **LinkedIn:** [linkedin.com/in/icaro-ramos-r](https://www.linkedin.com/in/icaro-ramos-r/)
- **Email:** [icaroelt@gmail.com](mailto:icaroelt@gmail.com)
