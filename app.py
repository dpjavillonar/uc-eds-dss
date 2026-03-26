import streamlit as st
import numpy as np
import pandas as pd
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import plotly.graph_objects as go
import streamlit.components.v1 as components

# --- 1. PAGE CONFIG & UI STYLING ---
st.set_page_config(
    page_title="UC EDS DSS - Official", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# --- 2. HARDWARE CONSTANTS ---
W_S1 = 27
W_S2 = 27
W_FANS = 130
W_PROJ = 300
W_PC = 150 
PHP_PER_KWH = 7.55

# --- 3. PURE CSS STYLING ---
st.markdown("""
    <style>
    .block-container {
        padding-top: 2rem !important; 
        padding-bottom: 0rem !important;
        max-width: 98%;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    /* Sleek, dark green gradient background */
    .stApp {
        background: linear-gradient(to bottom right, #1a3a26, #09170e);
    }
    div[data-testid="stMetric"] {
        background-color: rgba(38, 39, 48, 0.6) !important; 
        border: 1px solid #464b5d; 
        border-radius: 8px;
        padding: 5px 15px !important;
    }
    .stAlert { 
        padding: 0.2rem 0.8rem !important; 
        margin-bottom: 0.2rem !important;
    }
    h3 { margin-bottom: 0rem !important; padding-bottom: 0.2rem !important; }
    h4 { margin-bottom: 0rem !important; padding-bottom: 0.5rem !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. CACHED FUZZY LOGIC ENGINE ---
@st.cache_resource
def build_fuzzy_engine():
    occ = ctrl.Antecedent(np.arange(0, 41, 1), 'occupancy')
    tmp = ctrl.Antecedent(np.arange(20, 41, 1), 'temp')
    rec = ctrl.Consequent(np.arange(0, 101, 1), 'energy_rec')

    occ.automf(3, names=['low', 'medium', 'high'])
    tmp['cool'] = fuzz.trimf(tmp.universe, [20, 20, 26]) 
    tmp['moderate'] = fuzz.trimf(tmp.universe, [24, 28, 32])
    tmp['hot'] = fuzz.trimf(tmp.universe, [30, 40, 40]) 
    rec.automf(3, names=['low', 'medium', 'high'])

    rule_list = [
        ctrl.Rule(occ['low'] & tmp['cool'], rec['low']),      
        ctrl.Rule(occ['low'] & tmp['moderate'], rec['low']),  
        ctrl.Rule(occ['low'] & tmp['hot'], rec['medium']),    
        ctrl.Rule(occ['medium'] & tmp['cool'], rec['low']),      
        ctrl.Rule(occ['medium'] & tmp['moderate'], rec['medium']), 
        ctrl.Rule(occ['medium'] & tmp['hot'], rec['high']),      
        ctrl.Rule(occ['high'] & tmp['cool'], rec['medium']),     
        ctrl.Rule(occ['high'] & tmp['moderate'], rec['high']),   
        ctrl.Rule(occ['high'] & tmp['hot'], rec['high'])         
    ]
    return ctrl.ControlSystem(rule_list), rec

energy_ctrl, energy_rec = build_fuzzy_engine()
sim = ctrl.ControlSystemSimulation(energy_ctrl)

# --- 5. MAIN SCREEN: LOGO & TITLE ---
# Logo sits right at the top, much larger
try:
    st.image("UC_Official_Logo.png", width=350)
except FileNotFoundError:
    pass


# --- 6. STRICT 3-COLUMN LAYOUT ---
col_in, col_mid, col_out = st.columns([1, 1.2, 1.6], gap="medium")

# ==========================================
# COLUMN 1: CONFIGURATION & INPUTS
# ==========================================
with col_in:
    st.markdown("#### CONFIGURATION")
    room_type = st.radio("Mode:", ["Typical Classroom", "Computer Lab"], horizontal=True)
    proj_override = st.toggle("Projector Active", value=False)
    
    in_occ = st.slider("Students", 0, 40, 24) 
    in_tmp = st.slider("Temp (°C)", 20, 40, 34) 

    num_pcs = 0 
    if room_type == "Computer Lab":
        num_pcs = st.number_input("💻 Active PCs", min_value=0, max_value=30, value=20, step=1)

# --- SIMULATION CALCULATIONS ---
sim.input['occupancy'] = in_occ
sim.input['temp'] = in_tmp
sim.compute()
out_val = sim.output['energy_rec']

if in_occ == 0:
    draw_lights, draw_fans = 0, 0
    rec_lights, rec_fans = "OFF", "OFF"
else:
    if in_occ > 20 or out_val > 70: 
        draw_lights, rec_lights = W_S1 + W_S2, "FULL (S1 & S2)"
    elif in_occ > 0 or out_val > 35: 
        draw_lights, rec_lights = W_S1, "DIM (Switch 1)"
    else: 
        draw_lights, rec_lights = 0, "OFF"

    if out_val > 65 or in_tmp >= 27: 
        draw_fans, rec_fans = W_FANS, "HIGH"
    elif out_val > 40 or in_tmp >= 24: 
        draw_fans, rec_fans = W_FANS * 0.6, "MEDIUM"
    else: 
        draw_fans, rec_fans = 0, "LOW/OFF"
        
calc_pc_load = num_pcs * W_PC
active_w = draw_lights + draw_fans + (W_PROJ if proj_override else 0) + calc_pc_load
peak_w = (W_S1 + W_S2) + W_FANS + W_PROJ + calc_pc_load 

if peak_w == 0: peak_w = 1

monthly_base_php = (peak_w/1000 * 10 * 22 * PHP_PER_KWH)
Energy_draw_php = (active_w/1000 * 10 * 22 * PHP_PER_KWH)
savings_php = max(0, monthly_base_php - Energy_draw_php)
crr_percentage = (savings_php / monthly_base_php) * 100

if in_occ == 0:
    eff_score = max(0, (1 - (active_w / peak_w)) * 100) if active_w > 0 else 100.0
else:
    eff_score = 100 - out_val

# --- SESSION STATE & IMMEDIATE GRAPH INITIALIZATION ---
if 'is_initialized' not in st.session_state:
    st.session_state.history_time = [1, 2, 3, 4, 5]
    st.session_state.history_base = [peak_w] * 5
    st.session_state.history_opt = [active_w] * 5
    st.session_state.time_step = 5
    st.session_state.is_initialized = True
else:
    st.session_state.time_step += 1
    st.session_state.history_time.append(st.session_state.time_step)
    st.session_state.history_base.append(peak_w)
    st.session_state.history_opt.append(active_w)
    
    st.session_state.history_time = st.session_state.history_time[-25:]
    st.session_state.history_base = st.session_state.history_base[-25:]
    st.session_state.history_opt = st.session_state.history_opt[-25:]

# ==========================================
# COLUMN 2: CONSUMPTION & ACTIONS
# ==========================================
with col_mid:
    st.markdown("#### CONSUMPTION")
    m1, m2 = st.columns(2)
    m1.metric("Energy Draw", f"{int(active_w)}W")
    m2.metric("Monthly Savings", f"₱{savings_php:,.0f}")
    
    st.markdown("#### SYSTEM ACTIONS")
    
    if rec_lights == "FULL (S1 & S2)": st.error(f"💡 LIGHTS: {rec_lights}")
    elif rec_lights == "DIM (Switch 1)": st.warning(f"💡 LIGHTS: {rec_lights}")
    else: st.info(f"💡 LIGHTS: {rec_lights}")

    if rec_fans == "HIGH": st.error(f"🌀 FANS: {rec_fans}")
    elif rec_fans == "MEDIUM": st.warning(f"🌀 FANS: {rec_fans}")
    else: st.success(f"🌀 FANS: {rec_fans}")
    
    if proj_override: 
        if in_occ == 0: st.error("🎥 PROJECTOR: LEFT ON (WASTE)")
        else: st.error("🎥 PROJECTOR: ACTIVE")
            
    if room_type == "Computer Lab":
        if in_occ == 0 and num_pcs > 0: st.error(f"💻 PCs: {num_pcs} UNITS RUNNING (WASTE)")
        elif num_pcs > in_occ and in_occ > 0: st.warning(f"💻 PCs: {num_pcs} Active (Only {in_occ} needed)")

    if in_occ == 0: 
        mode, desc = "Vacant", "Room empty. Standby forced."
    elif out_val < 35: 
        mode, desc = "Conservation", f"Low load ({in_tmp}°C)."
    elif out_val < 70: 
        mode, desc = "Balanced", f"Moderate demand ({in_occ} users)."
    else: 
        mode, desc = "Performance", f"High load ({in_tmp}°C)."
    
    st.info(f"**Status:** {mode} — {desc}")

# ==========================================
# COLUMN 3: ANALYTICS & PLOTLY GRAPH
# ==========================================
with col_out:
    st.markdown("#### ANALYTICS")
    c1, c2 = st.columns(2)
    
    eff_delta = "-WASTE" if (in_occ == 0 and active_w > 0) else None
    eff_delta_color = "inverse" if eff_delta else "normal"
    c1.metric("Efficiency", f"{eff_score:.1f}%", delta=eff_delta, delta_color=eff_delta_color)
    c2.metric("CRR", f"{crr_percentage:.1f}%")
    
    # --- HIGHLY READABLE PLOTLY GRAPH WITH IN-GRAPH LABELS ---
    fig = go.Figure()

    # Baseline Line
    fig.add_trace(go.Scatter(
        x=st.session_state.history_time, y=st.session_state.history_base, 
        mode='lines', name='Baseline', line=dict(color='#FF4B4B', width=3)
    ))
    # Optimized Line
    fig.add_trace(go.Scatter(
        x=st.session_state.history_time, y=st.session_state.history_opt, 
        mode='lines', name='Optimized', line=dict(color='#00FF00', width=3)
    ))

    # Add text labels inside the graph anchored to the most recent data point
    last_x = st.session_state.history_time[-1]
    last_base_y = st.session_state.history_base[-1]
    last_opt_y = st.session_state.history_opt[-1]

    fig.add_annotation(x=last_x, y=last_base_y, text="Baseline", showarrow=False, 
                       yshift=15, font=dict(color="#FF4B4B", size=12, weight="bold"))
    fig.add_annotation(x=last_x, y=last_opt_y, text="Optimized", showarrow=False, 
                       yshift=-15, font=dict(color="#00FF00", size=12, weight="bold"))

    fig.update_layout(
        height=180,  # Compact height to fit screen
        margin=dict(l=0, r=20, t=10, b=0), # Remove dead space
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        xaxis=dict(visible=False), # Hide X axis numbers for a cleaner look
        yaxis=dict(gridcolor='#333333', title="Watts", title_font=dict(size=10))
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
  # --- DYNAMIC EXECUTIVE SUMMARY (Improved Logic) ---
    load_factor = (active_w / peak_w) * 100 if peak_w > 0 else 0
    
    # Priority 1: Check for Waste (Empty room with power draw)
    if in_occ == 0 and active_w > 0:
        theme, icon, title = "error", "🚨", "CRITICAL: Energy Waste"
        detail = "Room is vacant but equipment remains active. Manual override recommended."
        
    # Priority 2: Check for High Demand (Fans High OR Both Light Switches On)
    elif rec_fans == "HIGH" or rec_lights == "FULL (S1 & S2)":
        theme, icon, title = "warning", "🔥", "PEAK DEMAND"
        detail = f"Running at full power to keep {in_occ} students comfortable at {in_tmp}°C."
        
    # Priority 3: Check for Mid-Level operation (Fans Medium OR One Light Switch)
    elif rec_fans == "MEDIUM" or rec_lights == "DIM (Switch 1)":
        theme, icon, title = "info", "⚖️", "BALANCED LOAD"
        detail = "Balancing power usage with the current number of people and temperature."
        
    # Priority 4: Everything is low/off
    else:
        theme, icon, title = "success", "✅", "MAX SAVINGS"
        detail = "The room is cool and has few or no people. The system is saving as much energy as possible."

    # Render the summary box
    summary_text = f"**{icon} {title}**\n\n*{detail}*"
    
    if theme == "error": 
        st.error(summary_text)
    elif theme == "warning": 
        st.warning(summary_text)
    elif theme == "success": 
        st.success(summary_text)
    else: 
        st.info(summary_text)