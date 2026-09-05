from flask import Flask, render_template, request, jsonify
from enum import Enum
from collections import deque
import copy

app = Flask(__name__)

class ProcessState(Enum):
    NEW = "New"
    READY = "Ready"
    RUNNING = "Running"
    WAITING = "Waiting"
    TERMINATED = "Terminated"

class Process:
    def __init__(self, pid, arrival, burst, priority=0, io_requests=None):
        self.pid = pid
        self.arrival = arrival
        self.burst = burst
        self.remaining_burst = burst
        self.priority = priority
        self.io_requests = io_requests or []
        self.state = ProcessState.NEW
        self.state_history = []
        self.current_io = None
        self.io_remaining = 0
        
    def add_state_transition(self, new_state, time):
        if self.state != new_state:
            self.state_history.append({
                'from': self.state.value,
                'to': new_state.value,
                'time': time
            })
            self.state = new_state
    
    def has_io_at_time(self, time):
        for io_time, io_duration in self.io_requests:
            if io_time <= time < io_time + io_duration:
                return True, io_duration - (time - io_time)
        return False, 0

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/simulate", methods=["POST"])
def simulate():
    data = request.get_json()
    processes_data = data["processes"]
    algo = data["algorithm"]
    quantum = int(data["quantum"]) if data["quantum"] else 2

    processes = []
    for p_data in processes_data:
        io_requests = p_data.get("io_requests", [])
        process = Process(
            pid=p_data["pid"],
            arrival=p_data.get("arrival", 0),
            burst=p_data["burst"],
            priority=p_data.get("priority", 0),
            io_requests=io_requests
        )
        processes.append(process)

    timeline = []
    state_transitions = []
    current_time = 0

    if algo == "FCFS":
        processes.sort(key=lambda x: (x.arrival, x.pid))
        ready_queue = []
        time = 0
        i = 0
        
        while i < len(processes) or ready_queue:
            while i < len(processes) and processes[i].arrival <= time:
                processes[i].add_state_transition(ProcessState.READY, time)
                ready_queue.append(processes[i])
                i += 1
            
            if not ready_queue:
                if i < len(processes):
                    time = processes[i].arrival
                else:
                    break
                continue
            
            current = ready_queue.pop(0)
            current.add_state_transition(ProcessState.RUNNING, time)
            
            run_time = current.remaining_burst
            timeline.append({"pid": current.pid, "start": time, "end": time + run_time})
            current.remaining_burst = 0
            time += run_time
            
            io_occurred = False
            for io_time, io_duration in current.io_requests:
                if io_time < time and io_time + io_duration > time - run_time:
                    current.add_state_transition(ProcessState.WAITING, time)
                    time += io_duration
                    current.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current)
                    io_occurred = True
                    break
            
            if not io_occurred:
                current.add_state_transition(ProcessState.TERMINATED, time)

    elif algo == "SJF":
        processes.sort(key=lambda x: x.arrival)
        ready_queue = []
        time = 0
        i = 0
        
        while i < len(processes) or ready_queue:
            while i < len(processes) and processes[i].arrival <= time:
                processes[i].add_state_transition(ProcessState.READY, time)
                ready_queue.append(processes[i])
                i += 1
            
            if not ready_queue:
                if i < len(processes):
                    time = processes[i].arrival
                else:
                    break
                continue
            
            ready_queue.sort(key=lambda x: x.remaining_burst)
            current = ready_queue.pop(0)
            current.add_state_transition(ProcessState.RUNNING, time)
            
            run_time = current.remaining_burst
            timeline.append({"pid": current.pid, "start": time, "end": time + run_time})
            current.remaining_burst = 0
            time += run_time
            
            io_occurred = False
            for io_time, io_duration in current.io_requests:
                if io_time < time and io_time + io_duration > time - run_time:
                    current.add_state_transition(ProcessState.WAITING, time)
                    time += io_duration
                    current.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current)
                    io_occurred = True
                    break
            
            if not io_occurred:
                current.add_state_transition(ProcessState.TERMINATED, time)

    elif algo == "SRTF":
        processes.sort(key=lambda x: x.arrival)
        ready_queue = []
        time = 0
        i = 0
        current_running = None
        context_switches = 0
        
        while i < len(processes) or ready_queue or current_running:
            while i < len(processes) and processes[i].arrival <= time:
                processes[i].add_state_transition(ProcessState.READY, time)
                ready_queue.append(processes[i])
                i += 1
            
            ready_queue.sort(key=lambda x: x.remaining_burst)
            
            if current_running and ready_queue:
                if ready_queue[0].remaining_burst < current_running.remaining_burst:
                    current_running.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current_running)
                    context_switches += 1
                    current_running = None
            
            if not current_running and ready_queue:
                current_running = ready_queue.pop(0)
                if current_running.state != ProcessState.RUNNING:
                    current_running.add_state_transition(ProcessState.RUNNING, time)
            
            if not current_running:
                if i < len(processes):
                    time = processes[i].arrival
                else:
                    break
                continue
            
            timeline.append({"pid": current_running.pid, "start": time, "end": time + 1})
            current_running.remaining_burst -= 1
            time += 1
            
            io_occurred = False
            for io_time, io_duration in current_running.io_requests:
                if io_time <= time and io_time + io_duration > time:
                    current_running.add_state_transition(ProcessState.WAITING, time)
                    time += io_duration
                    current_running.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current_running)
                    current_running = None
                    io_occurred = True
                    break
            
            if not io_occurred and current_running.remaining_burst == 0:
                current_running.add_state_transition(ProcessState.TERMINATED, time)
                current_running = None

    elif algo == "Priority":
        processes.sort(key=lambda x: x.arrival)
        ready_queue = []
        time = 0
        i = 0
        
        while i < len(processes) or ready_queue:
            while i < len(processes) and processes[i].arrival <= time:
                processes[i].add_state_transition(ProcessState.READY, time)
                ready_queue.append(processes[i])
                i += 1
            
            if not ready_queue:
                if i < len(processes):
                    time = processes[i].arrival
                else:
                    break
                continue
            
            ready_queue.sort(key=lambda x: x.priority)
            current = ready_queue.pop(0)
            current.add_state_transition(ProcessState.RUNNING, time)
            
            run_time = current.remaining_burst
            timeline.append({"pid": current.pid, "start": time, "end": time + run_time})
            current.remaining_burst = 0
            time += run_time
            
            io_occurred = False
            for io_time, io_duration in current.io_requests:
                if io_time < time and io_time + io_duration > time - run_time:
                    current.add_state_transition(ProcessState.WAITING, time)
                    time += io_duration
                    current.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current)
                    io_occurred = True
                    break
            
            if not io_occurred:
                current.add_state_transition(ProcessState.TERMINATED, time)

    elif algo == "Round Robin":
        processes.sort(key=lambda x: x.arrival)
        ready_queue = deque()
        time = 0
        i = 0
        context_switches = 0
        
        while i < len(processes) or ready_queue:
            while i < len(processes) and processes[i].arrival <= time:
                processes[i].add_state_transition(ProcessState.READY, time)
                ready_queue.append(processes[i])
                i += 1
            
            if not ready_queue:
                if i < len(processes):
                    time = processes[i].arrival
                else:
                    break
                continue
            
            current = ready_queue.popleft()
            if current.state != ProcessState.RUNNING:
                current.add_state_transition(ProcessState.RUNNING, time)
            
            run_time = min(quantum, current.remaining_burst)
            timeline.append({"pid": current.pid, "start": time, "end": time + run_time})
            current.remaining_burst -= run_time
            time += run_time
            
            while i < len(processes) and processes[i].arrival <= time:
                processes[i].add_state_transition(ProcessState.READY, time)
                ready_queue.append(processes[i])
                i += 1
            
            io_occurred = False
            for io_time, io_duration in current.io_requests:
                if io_time <= time and io_time + io_duration > time:
                    current.add_state_transition(ProcessState.WAITING, time)
                    time += io_duration
                    current.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current)
                    io_occurred = True
                    break
            
            if not io_occurred:
                if current.remaining_burst > 0:
                    current.add_state_transition(ProcessState.READY, time)
                    ready_queue.append(current)
                    context_switches += 1
                else:
                    current.add_state_transition(ProcessState.TERMINATED, time)

    total_time = time
    
    all_transitions = []
    for process in processes:
        all_transitions.extend(process.state_history)
    
    all_transitions.sort(key=lambda x: x['time'])
    
    def calculate_metrics(processes, timeline):
        metrics = []
        for p in processes:
            finish_times = [seg["end"] for seg in timeline if seg["pid"] == p.pid]
            finish_time = max(finish_times) if finish_times else 0
            
            first_cpu_times = [seg["start"] for seg in timeline if seg["pid"] == p.pid]
            first_cpu = min(first_cpu_times) if first_cpu_times else 0
            
            arrival = p.arrival
            burst = p.burst
            
            turnaround_time = finish_time - arrival
            waiting_time = turnaround_time - burst
            response_time = first_cpu - arrival
            
            metrics.append({
                "pid": p.pid,
                "arrival": arrival,
                "burst": burst,
                "finish": finish_time,
                "turnaround": turnaround_time,
                "waiting": waiting_time,
                "response": response_time
            })
        
        avg_waiting = sum(m["waiting"] for m in metrics) / len(metrics) if metrics else 0
        avg_turnaround = sum(m["turnaround"] for m in metrics) / len(metrics) if metrics else 0
        avg_response = sum(m["response"] for m in metrics) / len(metrics) if metrics else 0
        
        cpu_time = sum(seg["end"] - seg["start"] for seg in timeline if seg["pid"] != "IDLE")
        cpu_utilization = (cpu_time / total_time * 100) if total_time > 0 else 0
        
        throughput = len(processes) / total_time if total_time > 0 else 0
        
        return {
            "process_metrics": metrics,
            "averages": {
                "waiting": round(avg_waiting, 2),
                "turnaround": round(avg_turnaround, 2),
                "response": round(avg_response, 2)
            },
            "system_metrics": {
                "cpu_utilization": round(cpu_utilization, 2),
                "throughput": round(throughput, 3)
            }
        }
    
    performance_metrics = calculate_metrics(processes, timeline)
    
    return jsonify({
        "timeline": timeline, 
        "total": total_time,
        "performance": performance_metrics,
        "state_transitions": all_transitions,
        "context_switches": context_switches if 'context_switches' in locals() else 0
    })


if __name__ == "__main__":
    app.run(debug=True)
