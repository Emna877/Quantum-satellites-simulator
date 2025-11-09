# Real-Time CubeSat Simulation Implementation Guide

## Project Overview
Build a continuous-timeline satellite simulation that propagates orbital dynamics in real-time, injects environmental and adversarial events, logs comprehensive telemetry for machine learning analysis, and streams live visualization data to a web-based Cesium viewer.

---

## Phase 1: Core Simulation Infrastructure

### Step 1.1: Design Comprehensive Satellite State Model
Create a data structure that captures all physical and operational parameters of the satellite at any given moment.

**State components to define:**
- **Orbital parameters**: Position vector in Earth-Centered Fixed frame, velocity vector, altitude above sea level, current orbital period
- **Attitude representation**: Quaternion for 3D orientation, angular velocity vector for rotation rates
- **Power system metrics**: Battery charge percentage, solar panel current output, total power consumption by all systems, instantaneous charging rate
- **Thermal state**: Internal temperature of electronics bay, external skin temperature, current heat dissipation rate
- **Communication metrics**: Received signal strength at ground station, packet loss percentage, uplink and downlink data rates
- **Environmental exposure**: Accumulated radiation dose, current atmospheric drag coefficient, boolean flag for eclipse state
- **Component health**: Status dictionary for each subsystem (operational, degraded, failed), error counters, timestamp of last commanded action

**Design considerations:**
- Use strongly-typed data structures for validation
- Include timestamp with every state snapshot
- Ensure all units are clearly documented
- Design for efficient serialization to CSV and JSON formats

### Step 1.2: Build Orekit Propagation Wrapper
Create an interface between the simulation engine and the Orekit astrodynamics library for high-fidelity orbital mechanics.

**Implementation tasks:**
- Initialize Java Virtual Machine with correct Orekit JAR files
- Load orekit-data directory containing Earth orientation parameters, leap seconds, and gravity field coefficients
- Parse Two-Line Element sets or Keplerian elements to initialize orbit
- Configure numerical propagator with appropriate force models for Low Earth Orbit
- Add perturbations: Earth gravity harmonics, atmospheric drag with density models, solar radiation pressure, third-body gravity from Sun and Moon
- Implement coordinate frame transformations between inertial and Earth-fixed frames
- Create time-step function that advances propagator by exactly one second
- Extract position, velocity, and derived quantities from propagator state
- Handle edge cases: propagator initialization failures, numerical instabilities, coordinate singularities

**Validation approach:**
- Compare propagated orbit against published ephemeris for ISS
- Verify orbital period matches theoretical calculation
- Check position accuracy over multiple revolutions
- Test propagation through eclipse transitions and attitude changes

### Step 1.3: Implement Simulation Clock Manager
Build a clock system that synchronizes simulated time with real wall-clock time while providing control over simulation speed.

**Clock functionality:**
- Track two independent timelines: simulated mission time and actual wall-clock elapsed time
- Maintain speed multiplier parameter that controls simulation rate relative to real-time
- Calculate lag between where simulation should be and where it actually is
- Provide pause mechanism that freezes simulation time while wall-clock continues
- Implement resume function that re-synchronizes timelines without jumps
- Support variable speed: slower than real-time for debugging, faster for data generation
- Create async sleep function that maintains precise timing between ticks
- Handle system clock adjustments and daylight saving transitions

**Control interface requirements:**
- Accept commands to pause and resume at any moment
- Allow speed changes during active simulation
- Provide query methods for current simulation time and lag status
- Log timing statistics for performance monitoring

### Step 1.4: Construct Main Simulation Loop
Orchestrate all simulation components in a continuous execution loop that drives the entire system.

**Loop sequence per tick:**
1. **Event generation phase**: Query event manager for any scheduled or random events that should occur at current simulation time
2. **Event application phase**: Apply effects of all active events to satellite state (modify position for GPS spoofing, reduce battery for power drain, etc.)
3. **Physics propagation phase**: Advance Orekit propagator by one time step to get updated orbital state from gravitational and perturbative forces
4. **State synchronization phase**: Merge propagated orbital elements with existing satellite state while preserving subsystem data
5. **Subsystem update phase**: Execute models for power, thermal, communication, and other subsystems that operate independently of orbital mechanics
6. **Logging phase**: Write current state and all events to persistent storage files
7. **Streaming phase**: Generate CZML packet and push to connected WebSocket clients for live visualization
8. **Clock advance phase**: Increment simulation time by time-step duration
9. **Synchronization phase**: Sleep until wall-clock catches up to maintain real-time pacing

**Error handling strategy:**
- Catch propagation failures and attempt recovery with reduced time step
- Log all exceptions with full context for debugging
- Implement graceful degradation when subsystems fail
- Provide checkpointing to restart from last known good state

---

## Phase 2: Event System Architecture

### Step 2.1: Define Event Base Class Structure
Establish common interface and properties for all simulation events.

**Base event attributes:**
- Unique event identifier for tracking
- Timestamp when event occurs in simulation time
- Event type enumeration for classification
- Severity level for prioritization and filtering
- Parameter dictionary containing event-specific data
- Boolean flag indicating if event represents an attack versus natural phenomenon
- Duration field for events with temporal extent

**Base event methods:**
- Apply function that modifies satellite state according to event physics
- Serialize function for logging to JSON format
- Validation function to ensure parameters are physically reasonable
- String representation for human-readable logging

### Step 2.2: Implement Environmental Event Classes
Create events representing natural space environment phenomena that affect satellite operations.

#### Solar Flare Event
**Trigger mechanism**: Random occurrence based on solar activity probability or scheduled during high solar activity periods

**Physical effects on satellite:**
- Increase radiation dose rate by 5 to 50 milliGray per hour depending on flare intensity
- Elevate external temperature by 10 to 30 degrees Celsius from increased solar irradiance
- Degrade communication signal strength by 5 to 15 dB due to ionospheric disturbances
- Potentially trigger single-event upsets in electronics if intensity exceeds threshold

**Event parameters**: Intensity scale from 1 to 10, duration in seconds, peak time offset

**ML detection signatures**: Correlated changes in multiple subsystems, gradual onset and decay, matches solar weather data if available

#### Eclipse Transition Events
**Entry trigger**: Computed from orbital geometry when satellite enters Earth's shadow

**Effects during eclipse:**
- Set eclipse state flag to true
- Reduce solar panel current to zero immediately
- Begin battery discharge at nominal rate plus current load
- Decrease external temperature due to loss of solar heating
- Activate thermal heaters if temperature drops below threshold

**Exit trigger**: Computed when satellite emerges from shadow

**Effects after exit:**
- Clear eclipse state flag
- Restore solar panel current based on panel orientation and Sun angle
- Resume battery charging if charge level below maximum
- Increase external temperature as solar radiation resumes

**ML signatures**: Predictable periodic pattern matching orbital period, simultaneous loss of solar power and temperature change

#### Micrometeoroid Impact Event
**Trigger**: Random occurrence with very low probability per time step

**Impact physics:**
- Transfer momentum to satellite causing impulsive change in angular velocity
- Potential damage to solar panels reducing power generation efficiency
- Possible degradation of sensors in impact zone
- Create debris that may damage other components

**Event parameters**: Impactor mass in grams, velocity vector in kilometers per second, impact location on satellite body

**ML signatures**: Sudden unexplained change in attitude, power loss without eclipse, sensor malfunctions

#### Atmospheric Drag Variation Event
**Trigger**: Based on geomagnetic storm models or scheduled during high solar activity

**Effects on orbit:**
- Multiply atmospheric drag coefficient by factor between 1.5 and 3.0
- Accelerate orbital decay rate
- Increase frequency of station-keeping maneuvers required
- Elevate external temperature from increased friction heating

**Event parameters**: Drag multiplier factor, duration in seconds, altitude dependence curve

**ML signatures**: Faster than expected altitude loss, increased atmospheric interaction

#### Geomagnetic Storm Event
**Trigger**: Linked to solar activity index (Kp index above threshold)

**Storm effects:**
- Dramatically increase radiation dose rate by 10 to 100 milliGray per hour
- Severely degrade radio communications with signal strength loss of 10 to 40 dB
- Amplify atmospheric drag through thermospheric heating
- Induce electrical currents in satellite structure potentially affecting electronics

**Event parameters**: Kp index value from 5 to 9, storm duration in hours, peak intensity time

### Step 2.3: Implement Attack Event Classes
Create adversarial events representing deliberate interference with satellite operations.

#### GPS Spoofing Attack
**Trigger**: User-configured probability or scheduled attack scenario

**Attack mechanics:**
- Inject false position offset ranging from 10 meters to 10 kilometers
- Add velocity drift that accumulates over time
- Maintain consistency to avoid immediate detection
- Optional: make offset time-varying to simulate sophisticated attacker

**Event parameters**: Position offset vector, velocity drift rate, attack duration, sophistication level

**ML detection signatures**: Position diverges from propagated orbit, inconsistent with ground station observations, sudden jump or gradual drift pattern

#### Command Injection Attack
**Trigger**: Represents unauthorized command executed on satellite

**Attack actions:**
- Execute unscheduled maneuver changing satellite attitude
- Modify quaternion to random or targeted orientation
- Change angular velocity creating unwanted rotation
- Potentially destabilize attitude control system

**Event parameters**: Target quaternion, impulse magnitude, timing pattern

**ML signatures**: Attitude change without corresponding ground command log, unexpected propellant usage, unusual command sequence

#### Communication Jamming Attack
**Trigger**: Random or targeted against specific ground contacts

**Jamming effects:**
- Reduce signal strength by 30 to 80 dB making communication impossible
- Increase packet loss rate to 50% to 100%
- Block uplink commands preventing ground control
- Block downlink telemetry preventing monitoring

**Event parameters**: Jamming power level, frequency bands affected, geographic source location, duration

**ML signatures**: Communication loss without eclipse explanation, satellite power and orientation nominal, selective frequency jamming

#### Laser Dazzling Attack
**Trigger**: Ground-based laser directed at satellite sensors

**Dazzle effects:**
- Saturate star tracker or Sun sensor preventing accurate attitude determination
- Temporary or permanent damage to optical detectors
- Degrade attitude control performance from bad sensor data
- Potential cascading failure of attitude determination system

**Event parameters**: Laser wavelength, power density, exposure duration, affected sensor

**ML signatures**: Sensor saturation events, attitude determination errors, loss of pointing accuracy, correlation with ground station passes

#### Stealthy Power Drain Attack
**Trigger**: Represents malware or compromised software increasing power consumption

**Attack mechanism:**
- Multiply power consumption by factor between 1.5 and 3.0
- No corresponding increase in operational activity to justify power use
- Drain battery faster than expected during eclipse
- Potentially deplete battery leading to mission failure

**Event parameters**: Power multiplier, activation pattern, persistence

**ML signatures**: Battery discharge rate anomaly, no thermal increase matching power, no commanded operations active

#### Thermal Sabotage Attack
**Trigger**: Compromise of thermal control system or heater control

**Attack effects:**
- Force heaters to maximum power overheating components
- Disable heaters allowing excessive cooling
- Oscillate thermal control creating temperature cycling stress
- Potentially damage temperature-sensitive components

**Event parameters**: Heater override setting, target temperature, duration

**ML signatures**: Temperature excursions outside nominal range, heater activity inconsistent with temperature, no environmental explanation

### Step 2.4: Build Event Manager System
Create centralized event orchestration and scheduling system.

**Manager responsibilities:**
- Maintain priority queue of scheduled events sorted by timestamp
- Generate random events each time step based on probability distributions
- Track active events that have temporal duration
- Apply all relevant events to satellite state in correct order
- Validate that combined event effects don't create impossible physical states
- Label every event with ground truth attack classification for ML training
- Maintain event history for correlation analysis
- Provide interface for user to inject custom events during simulation

**Event generation strategy:**
- Roll random number each tick for each event type
- Compare against configured probability to determine if event occurs
- For scheduled events, check if current time matches trigger time
- Support event chains where one event can trigger another
- Implement mutual exclusion for incompatible simultaneous events

**State validation after events:**
- Ensure battery percentage stays between 0% and 100%
- Verify position remains within plausible orbital envelope
- Check temperature stays within component survival limits
- Validate that component health degradation is monotonic

---

## Phase 3: Subsystem Physical Models

### Step 3.1: Power Subsystem Model
Implement detailed electrical power generation, storage, and consumption model.

**Solar power generation:**
- Calculate Sun vector relative to satellite from ephemeris
- Determine solar panel orientation from attitude quaternion
- Compute incident angle between panel normal and Sun vector
- Apply solar panel efficiency factor (typically 28% for CubeSat panels)
- Account for solar distance variations affecting solar constant
- Reduce output during eclipse to zero

**Battery dynamics:**
- Model lithium-ion battery with capacity in watt-hours
- Implement charging curve with reduced rate near full capacity
- Calculate discharge rate from sum of component power draws
- Apply depth-of-discharge limits to preserve battery health
- Include temperature effects on capacity and efficiency
- Track charge/discharge cycle count for degradation model

**Component power consumption:**
- Radio transceiver: 2 to 5 watts during transmission, lower when receiving
- Onboard computer: 0.5 to 2 watts depending on processing load
- Attitude sensors: 0.1 to 1 watt each for gyroscopes, magnetometers, star trackers
- Attitude actuators: 1 to 3 watts for reaction wheels or magnetorquers
- Thermal heaters: 5 to 15 watts when active
- Scientific payloads: Variable based on instrument type

**State tracking:**
- Current battery charge percentage
- Instantaneous solar panel current in amperes
- Total power consumption in watts
- Net charging or discharging rate
- Time until battery depletion at current rate
- Time until full charge at current rate

### Step 3.2: Thermal Subsystem Model
Implement heat balance model accounting for all thermal energy sources and sinks.

**Heat input sources:**
- Direct solar radiation: Solar flux multiplied by satellite cross-sectional area and absorptivity coefficient
- Reflected sunlight (albedo): Earth albedo factor times solar flux times visible area factor
- Earth infrared emission: Earth thermal emission times view factor from satellite to Earth
- Internal heat dissipation: All electrical power not used for mechanical work converts to heat

**Heat removal mechanisms:**
- Thermal radiation to space: Stefan-Boltzmann law with satellite surface area, emissivity, and fourth power of temperature
- Conduction through satellite structure: Thermal conductivity between different components
- Heat storage: Temperature change depends on thermal mass and specific heat capacity

**Temperature calculations:**
- Solve energy balance equation: sum of inputs minus sum of outputs equals rate of thermal energy storage
- Update internal temperature using thermal mass and specific heat
- Update external skin temperature separately with different thermal properties
- Apply thermal control: activate heaters when temperature drops below lower limit, increase radiator effectiveness when above upper limit

**Critical temperature monitoring:**
- Track temperatures of battery, computer, radio, and other temperature-sensitive components
- Flag thermal emergencies when limits exceeded
- Trigger thermal safe mode if overheating or extreme cold detected

### Step 3.3: Communication Link Budget Model
Calculate signal strength and data rate between satellite and ground stations.

**Link budget components:**
- Transmitter power: Satellite radio output in dBm
- Transmit antenna gain: Directivity of satellite antenna in dBi
- Free space path loss: Function of distance and frequency using Friis transmission equation
- Atmospheric absorption: Frequency-dependent loss through atmosphere, angle-dependent via airmass calculation
- Receive antenna gain: Ground station antenna directivity in dBi
- System noise figure: Combined receiver noise in dB
- Background noise: Thermal noise floor plus sky temperature contribution

**Signal quality calculations:**
- Compute received power in dBm by summing gains and subtracting losses
- Calculate signal-to-noise ratio from received power minus noise floor
- Determine bit error rate from SNR using modulation scheme
- Compute packet loss percentage from bit error rate
- Calculate maximum data rate using Shannon-Hartley theorem

**Link geometry:**
- Compute slant range from satellite to ground station
- Calculate elevation angle at ground station
- Determine if line of sight exists (not blocked by Earth)
- Apply elevation mask (typically 5 to 10 degrees minimum)
- Account for atmospheric effects increasing with lower elevation

### Step 3.4: Radiation Environment Model
Track cumulative radiation exposure and model effects on satellite components.

**Radiation sources:**
- Van Allen belt trapped particles: Protons and electrons trapped in Earth's magnetic field, intensity varies with altitude and latitude
- South Atlantic Anomaly: Region where inner Van Allen belt dips close to Earth causing high radiation exposure
- Solar particle events: Energetic particles released during solar flares
- Galactic cosmic rays: Constant background from outside solar system

**Dose rate calculation:**
- Use orbital position to query radiation model (simplified trapped particle model or full AP-8/AE-8 models)
- Add contribution from current solar particle events if any active
- Sum galactic cosmic ray background
- Apply shielding factor based on satellite structural mass

**Cumulative effects:**
- Track total ionizing dose in kilorads
- Model single-event upset rate increasing with radiation intensity
- Simulate degradation of solar panels from accumulated dose
- Increase component failure probability with total dose exposure

---

## Phase 4: Comprehensive Data Logging for Machine Learning

### Step 4.1: Design Telemetry Database Schema
Create structured data format capturing all information needed for ML training.

**Primary telemetry CSV format:**
- Timestamp column in ISO 8601 format for precise time correlation
- Position columns: X, Y, Z coordinates in ECEF frame in meters
- Velocity columns: VX, VY, VZ in meters per second
- Altitude in meters above reference ellipsoid
- Attitude quaternion: four columns for W, X, Y, Z components
- Angular velocity: three columns for rotation rates in radians per second
- Battery percentage: 0 to 100 scale
- Solar current in amperes
- Power consumption in watts
- Internal temperature in Celsius
- External temperature in Celsius
- Signal strength in dBm
- Packet loss percentage
- Radiation dose rate in milliGray per hour
- Eclipse state: boolean or 0/1 integer
- Component health flags: one column per critical component
- Event type: enumeration or string identifier
- Event parameters: JSON string with all event data
- Attack flag: boolean indicating if any active event is an attack
- Attack type: specific attack classification if applicable

**One row per second of simulation time** to maintain uniform sampling rate and simplify time-series analysis.

### Step 4.2: Implement Event Logging System
Create detailed event log separate from telemetry for forensic analysis.

**Event JSON schema:**
- Event unique identifier
- Timestamp of event start
- Event end time for duration events
- Event type classification
- Severity level
- Source: random, scheduled, or user-injected
- All event parameters with units documented
- Attack classification and ground truth label
- Effects applied to state with before/after values
- Correlation IDs linking related events

**Logging strategy:**
- Write one JSON object per event to append-only file
- Include full context: satellite state at event time, active events, recent history
- Enable filtering by event type, time range, severity
- Support efficient search by maintaining index

### Step 4.3: Create Component Health History Logs
Track status changes of every satellite subsystem over time.

**Component health CSV columns:**
- Timestamp
- Component name identifier
- Current health state: operational, degraded, failed
- Performance metric: efficiency or capability percentage
- Error count: cumulative errors since start
- Last successful operation timestamp
- Estimated remaining lifetime
- Maintenance actions applied

**Components to track:**
- Solar panels (each panel individually)
- Battery cells
- Radio transceiver
- Onboard computer
- Attitude determination sensors
- Attitude control actuators
- Thermal heaters
- Scientific instruments

### Step 4.4: Prepare Feature Engineering Framework
Design the feature extraction process that will convert raw telemetry into ML model inputs.

**Temporal derivative features:**
- Compute first derivative (rate of change) for battery, temperature, altitude, and other slowly-varying quantities
- Calculate second derivative (acceleration) for position to detect anomalous forces
- Use finite differences over multiple time steps to reduce noise

**Deviation from physics model features:**
- Compare actual battery level against predicted level from power model
- Compute position error between actual state and propagated orbit
- Calculate temperature difference from thermal equilibrium prediction
- Measure attitude stability against expected damping

**Statistical window features:**
- Rolling mean over last 60 seconds to capture short-term trends
- Rolling standard deviation to detect increased variance
- Maximum and minimum values in sliding window
- Crossing counts of thresholds indicating oscillatory behavior

**Event correlation features:**
- Time since last event of each type
- Number of events in trailing time window
- Co-occurrence patterns of multiple event types
- Duration of current event if one is active

**Operational context features:**
- Current orbital phase: ascending, descending, over ground station
- Eclipse state and time until next transition
- Battery state of charge category: critical, low, nominal, high
- Communication link availability and quality

**Feature vector design:**
- Target approximately 100 to 200 features total
- Normalize all features to similar scales
- Handle missing values from sensor failures
- Document physical meaning and units of each feature

---

## Phase 5: Real-Time Streaming Infrastructure

### Step 5.1: Implement CZML Packet Generator
Convert satellite state to Cesium compatible visualization format.

**CZML document structure:**
- Document packet with simulation metadata: name, version, time bounds
- Satellite entity packet with all visualization properties
- Position property with time-tagged Cartesian coordinate array
- Orientation property with quaternion for 3D model orientation if using satellite model
- Path property showing ground track with configurable lead and trail times
- Label showing satellite name and optionally current state
- Point or model for satellite representation

**Position encoding:**
- Use epoch-based Cartesian position format for efficiency
- Encode positions as flat array: time offset in seconds, then X, Y, Z coordinates
- Include sufficient positions for smooth interpolation
- Transform from ECEF (or ECI) frame to Cesium's fixed frame coordinate system

**Visual state encoding:**
- Change path color based on satellite operational state: green for nominal, yellow for warning, red for critical
- Modify point size or model scale based on zoom level
- Show different icons for different satellite modes
- Add labels for active events or alerts

**Update strategy:**
- Batch positions in groups of 5 to 10 seconds to reduce network traffic
- Set lead time to 0 for real-time display without prediction
- Configure trail time to 3600 seconds to show one orbit of history
- Send incremental updates rather than full documents after initial load

### Step 5.2: Build WebSocket Streaming Server
Create WebSocket server that pushes updates to connected visualization clients.

**Server architecture:**
- Use asynchronous WebSocket library compatible with simulation event loop
- Listen on dedicated port separate from potential REST API
- Maintain list of connected clients for broadcast
- Handle client connection and disconnection gracefully

**Message protocol:**
- Define message types: CZML position update, full state snapshot, event notification, ML prediction alert
- Wrap each message with type field and timestamp
- Include sequence numbers for ordering and gap detection
- Support message acknowledgment for critical updates

**Connection management:**
- Accept new client connections at any time during simulation
- Send initial state snapshot to new clients for sync
- Remove disconnected clients from broadcast list
- Implement heartbeat to detect stale connections
- Limit maximum connected clients to prevent resource exhaustion

**Streaming optimization:**
- Compress messages using WebSocket compression extension
- Throttle update rate per client based on network conditions
- Queue messages if client falls behind and drop oldest if queue exceeds limit
- Prioritize critical alerts over routine position updates

### Step 5.3: Create Visualization Client Updates
Modify existing HTML viewer to consume real-time WebSocket stream.

**Client connection:**
- Establish WebSocket connection to server on page load
- Implement automatic reconnection with exponential backoff on disconnect
- Display connection status indicator in UI
- Buffer incoming messages if processing lags behind

**CZML integration:**
- Initialize Cesium viewer with base CZML document
- Process incremental CZML packets from WebSocket
- Update data sources without full reload for smooth animation
- Interpolate positions between updates for continuous motion

**State display panel:**
- Show current satellite parameters updated every second
- Display battery, temperature, signal strength with color-coded indicators
- List recent events in scrollable log
- Highlight active anomalies or attacks with prominent alerts

**Interactive controls:**
- Add pause/resume button that sends control message to server
- Provide speed control slider for simulation rate
- Implement event injection dialog for testing
- Enable camera tracking of satellite with toggle

### Step 5.4: Implement Telemetry Dashboard
Create web interface showing real-time plots and system health.

**Time-series plots:**
- Battery level over time with predicted depletion
- Temperature trends with limit lines
- Altitude decay curve with regression fit
- Signal strength during ground station passes

**System status indicators:**
- Component health matrix showing all subsystems
- Power budget pie chart with consumption by component
- Orbital parameters display with propagation accuracy
- Communication link status with next contact countdown

**Alert panel:**
- List active warnings and errors
- Show ML predictions with confidence levels
- Provide event timeline with color-coded markers
- Display recommended actions for operators

---

## Phase 6: Configuration and Control System

### Step 6.1: Design Hierarchical Configuration Schema
Create structured configuration allowing easy scenario definition.

**Configuration file format:**
Use YAML for human readability with nested structure:
- Simulation parameters: start time, duration, time step, real-time flag, speed multiplier
- Satellite definition: orbital elements or TLE, physical properties (mass, area, power capacity)
- Environment settings: enable/disable specific event types, set occurrence probabilities, configure force models
- Attack scenario: define attack types to include, set probabilities or schedules, configure sophistication levels
- Ground stations: list of station locations with antenna parameters
- Logging options: output file paths, data formats, sampling rates
- ML settings: feature extraction parameters, inference intervals, model paths

**Configuration inheritance:**
- Define base configuration with default values
- Allow scenario-specific configurations to override defaults
- Support configuration composition from multiple files
- Validate all parameters against allowed ranges

### Step 6.2: Implement Runtime Control Interface
Provide commands to control simulation during execution.

**Control commands:**
- PAUSE: Freeze simulation time while maintaining system state
- RESUME: Continue simulation from paused state
- SET_SPEED: Change simulation speed multiplier dynamically
- INJECT_EVENT: Force specific event to occur immediately with given parameters
- TRIGGER_ATTACK: Initiate attack scenario for testing detection
- RESET: Return simulation to initial conditions
- CHECKPOINT: Save complete current state for later restart
- RESTORE: Load simulation from previously saved checkpoint

**Command delivery methods:**
- WebSocket messages from web interface
- Command-line interface for scripting
- REST API for integration with other tools
- Configuration file watched for changes

**Safety interlocks:**
- Require confirmation for destructive commands
- Log all control actions with operator identity and timestamp
- Prevent conflicting simultaneous commands
- Validate command parameters before execution

### Step 6.3: Create Scenario Library
Build collection of predefined simulation scenarios for testing.

**Scenario types:**
- Nominal operations: No anomalies, validate normal behavior
- Single event tests: One specific event type to verify correct handling
- Multi-event stress test: High probability of all events to test robustness
- Attack campaigns: Realistic sequences of coordinated attacks
- Worst-case scenarios: Multiple simultaneous failures
- Historical replay: Recreate known satellite incidents

**Scenario parameters:**
- Duration ranging from hours to weeks
- Event probabilities tuned for scenario objectives
- Initial satellite state and orbital parameters
- Ground truth labels for validation

### Step 6.4: Build Simulation Orchestration Script
Create master script that runs complete simulation campaign.

**Script responsibilities:**
- Load configuration for batch of scenarios
- Initialize simulation engine for each scenario
- Execute simulation until completion or timeout
- Capture all outputs and logs
- Generate summary statistics
- Archive results with metadata
- Report any failures or anomalies during execution

**Batch processing features:**
- Run multiple scenarios in sequence
- Parallelize independent simulations on multi-core systems
- Continue batch even if individual scenarios fail
- Compare results across scenario variations
- Export aggregated dataset for ML training

---

## Implementation Timeline and Milestones

### Week 1: Core Foundation
**Objective**: Establish working propagation loop that runs continuously.

**Tasks:**
1. Create project directory structure with proper module organization
2. Implement satellite state data structure with all required fields
3. Integrate Orekit library and verify data loading
4. Build basic propagator wrapper that advances orbit by one second
5. Create simulation clock with real-time synchronization
6. Construct minimal main loop that propagates and prints position
7. Test: Run for one orbital period and verify position returns to start

**Deliverable**: Python script that propagates an orbit in real-time for at least one hour without errors.

### Week 2: Event System and Subsystems
**Objective**: Add environmental events and power/thermal subsystem models.

**Tasks:**
1. Define event base class and implement inheritance structure
2. Create environmental event classes: eclipse transitions, solar flare, atmospheric drag
3. Build event manager with priority queue and random generation
4. Implement power subsystem model with battery and solar panels
5. Implement thermal subsystem with heat balance equation
6. Integrate event application into main simulation loop
7. Test: Run 24-hour simulation with random events and verify battery doesn't violate constraints

**Deliverable**: Simulation that generates environmental events and updates subsystem states realistically.

### Week 3: Attack Events and Logging
**Objective**: Add adversarial events and comprehensive data logging for ML.

**Tasks:**
1. Implement attack event classes: GPS spoofing, jamming, command injection
2. Add attack probability configuration and trigger logic
3. Create telemetry CSV logger writing one row per second
4. Create event JSON logger with full event details
5. Implement component health tracking and logging
6. Label all events with ground truth attack classification
7. Test: Run simulation with attacks enabled and verify correct labeling in logs

**Deliverable**: Complete event system with logged dataset containing labeled normal and attack samples.

### Week 4: Streaming and Visualization
**Objective**: Enable real-time visualization through WebSocket streaming.

**Tasks:**
1. Build CZML packet generator from satellite state
2. Implement WebSocket server with asyncio
3. Integrate CZML streaming into main loop
4. Update HTML viewer to connect to WebSocket
5. Add state display panel showing current parameters
6. Implement visual state encoding with color-coded paths
7. Test: Visualize real-time orbit in Cesium viewer with smooth motion

**Deliverable**: Working real-time visualization showing satellite moving in Cesium with live telemetry display.

### Week 5: Configuration and Polish
**Objective**: Add configuration system and validate complete simulation.

**Tasks:**
1. Create YAML configuration schema and loader
2. Implement runtime control interface for pause/resume/speed
3. Build scenario library with multiple test cases
4. Add remaining subsystem models: communication link, radiation
5. Implement all remaining event types
6. Create simulation orchestration script for batch runs
7. Run 7-day simulation to generate training dataset

**Deliverable**: Production-ready simulation system with configuration and complete week-long dataset.

### Week 6: Validation and Dataset Quality
**Objective**: Verify simulation correctness and prepare ML handoff.

**Tasks:**
1. Compare propagated orbits against reference ephemeris
2. Validate subsystem models against theoretical predictions
3. Check event statistics match configured probabilities
4. Verify ground truth labels are 100% accurate
5. Inspect dataset for missing values or anomalies
6. Document feature extraction approach
7. Create ML handoff package with dataset and documentation

**Deliverable**: Validated dataset with quality metrics report ready for machine learning development.

---

## Success Criteria and Quality Gates

### Reliability Requirements
- Simulation must run continuously for minimum 7 days without crashes
- Propagation error must remain below 5 kilometers RMS for Low Earth Orbit
- No invalid physical states allowed (negative battery, impossible temperatures)
- All logged data must have valid values, no NaN or infinite entries

### Dataset Requirements
- Minimum 500,000 telemetry samples (approximately 6 days at 1 Hz)
- At least 10,000 total events logged
- Balanced dataset: 40-60% split between attack and natural events
- Each attack type must have minimum 500 examples
- Event labels must be 100% accurate with ground truth

### Performance Requirements
- Simulation must maintain real-time pace on standard hardware
- Maximum lag allowed: 10 seconds behind real-time during 24-hour run
- CZML updates must stream at minimum 0.5 Hz to viewers
- Telemetry logging must not cause simulation slowdown

### Validation Requirements
- Orbital period must match theoretical calculation within 1%
- Eclipse transitions must match geometric predictions within 10 seconds
- Battery energy balance must be conserved within 5% over full orbit
- Temperature predictions must match simplified equilibrium models within 10%
- Communication link budgets must agree with industry standard calculators within 2 dB

---

## ML Handoff Checklist

### Dataset Deliverables
- Primary telemetry CSV file with complete state history
- Event log JSON file with all event details
- Component health history CSV
- Configuration files used to generate data
- Data dictionary documenting all columns and units

### Model Baseline Deliverables
- Physical model predictions for battery level
- Propagated orbit positions for comparison
- Expected subsystem behaviors for nominal operations
- Statistical distributions of normal operating ranges

### Documentation Deliverables
- Feature extraction methodology document
- Known limitations and edge cases
- Validation results and accuracy metrics
- Simulation assumptions and simplifications
- Recommendations for feature engineering

### Code Deliverables
- Feature extraction Python module
- Data loading and preprocessing utilities
- Visualization scripts for exploratory analysis
- Train/test split function preserving temporal order

---

## Risk Mitigation Strategies

### Technical Risks
**Risk**: Orekit propagation becomes unstable over long runs
**Mitigation**: Implement adaptive time stepping, checkpoint regularly, validate against published ephemeris frequently

**Risk**: Event interactions create impossible states
**Mitigation**: Add comprehensive state validation after every event application, log warnings for boundary cases

**Risk**: Real-time synchronization drifts over extended runs
**Mitigation**: Periodically resync with system clock, monitor and log timing statistics, allow controlled speed variation

### Data Quality Risks
**Risk**: Dataset becomes imbalanced with too few attack examples
**Mitigation**: Configure attack probabilities to achieve desired distribution, generate multiple runs with different seeds

**Risk**: Event labels are incorrect reducing ML model accuracy
**Mitigation**: Implement rigorous testing of event classification, manual review sample of logs, cross-validate with event parameters

**Risk**: Missing or corrupted data in logs
**Mitigation**: Add data validation on write, implement atomic file operations, maintain backup logs

### Performance Risks
**Risk**: Simulation cannot maintain real-time with all models enabled
**Mitigation**: Profile code to identify bottlenecks, optimize critical sections, allow reduced-fidelity mode

**Risk**: Streaming overloads network or clients
**Mitigation**: Implement adaptive rate limiting, add compression, allow clients to request reduced update frequency

---

## Future Enhancements (Post-ML Phase)

### Advanced Features for Consideration
- Multi-satellite constellation simulations with inter-satellite links
- Ground station network with scheduling and handoffs
- Closed-loop control with ML predictions feeding back into simulation
- Realistic command and data handling system
- Orbit maintenance and collision avoidance maneuvers
- Hardware-in-the-loop integration for real satellite testing
- Distributed simulation across multiple processes or machines
- Real-time data assimilation from actual satellite telemetry

### ML Integration Ideas
- Deploy trained model in simulation for real-time anomaly detection during runs
- Use ML predictions to trigger defensive responses automatically
- Generate adversarial examples to stress-test detection algorithms
- Implement reinforcement learning agent for autonomous satellite operations
- Create digital twin that mirrors real satellite with ML-enhanced state estimation

---

## Questions to Address Before Implementation

1. What specific orbital regime should be simulated: Low Earth, Medium Earth, or Geostationary orbit?
2. What satellite mass, power capacity, and physical dimensions should be used as baseline?
3. Should Two-Line Elements from real satellites be used or idealized Keplerian orbits?
4. What ground station locations should be included in configuration?
5. What balance between environmental and attack events provides best ML training data?
6. Should simulation support human-in-the-loop operations or run fully automated?
7. What tools will be used for ML development: scikit-learn, TensorFlow, PyTorch, or others?
8. Should simulation generate additional synthetic data through parameter variations?

---

## Getting Started

**First Steps:**
1. Review this entire document and adjust event probabilities and scenario parameters
2. Set up Python development environment with Orekit and required dependencies
3. Begin with Week 1 tasks starting with propagator wrapper
4. Test each component individually before integration
5. Maintain detailed development log documenting decisions and issues

**Recommended Development Approach:**
- Build incrementally with frequent testing of each addition
- Commit working code to version control after each milestone
- Generate small datasets during development to validate logging
- Visualize intermediate results to catch errors early
- Document any deviations from this plan with rationale

**Ready to begin implementation?** Start with Step 1.2: Build Orekit Propagation Wrapper.
