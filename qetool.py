import subprocess
import os
import time
import pandas as pd
import numpy as np
import jinja2 as j2
from pseudo_tool import *

testcmd = (
    "echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope && "
    "export OMP_NUM_THREADS=1 && "
    "conda run -n qespresso mpirun -np 1 pw.x -in test.in"
)
default_params = {'celldm':6.765, 'ecutwfc':40, 'k':6}

class atom_position:
    atom : str
    x : float
    y : float
    z : float

    def __init__(self, atom : str, x : float, y : float, z : float):
        self.atom = atom
        self.x = x
        self.y = y
        self.z = z

    def __str__(self):
        return f"{self.atom} {self.x} {self.y} {self.z}"

class structure:
    """A QE-tool structure"""
    ibrav : int 
    celldm : float
    species : pd.DataFrame
    positions : list[atom_position]

    def __init__(self, positions : atom_position):
        species = []
        for position in positions:
            if position.atom not in species:
                species.append(position.atom)
        self.species = get_pseudo_data(species)
        self.positions = positions

    def positions_to_string(self):
        output = []
        for position in self.positions:
            output.append(str(position))
        return "\n".join(output)
    
    def get_nbnd(self):
        sum = 0
        for position in self.positions:
            sum += self.species.loc[position.atom, 'n_valance']
        return sum

    def to_params(self):
        output = {
            "nat":len(self.positions),
            "ntyp":len(self.species),
            "nbnd":int(self.get_nbnd()) + 4, # 4 IF METAL, THIS HAS TO BE ADAPTED,
            "species":define_species(self.species),
            "positions": self.positions_to_string()
            }
        if not np.isnan(self.ibrav):
            output.update({"ibrav":self.ibrav})
        else:
            output.update({"ibrav":2})
        return output



def generate_command(cpus, program="pw.x", input_path="test.in", threads=1):
    return (
        "echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope && "
        f"export OMP_NUM_THREADS={threads} && "
        f"conda run -n qespresso mpirun -np {cpus} {program} -in {input_path}"
    )

def run_logged_command(command, output_file="test.out", label=""):
    usagestart = time.time()
    with open(output_file, "w") as outfile:
        subprocess.run(command, shell=True, check=True, stdout=outfile, stderr=subprocess.STDOUT)
    usageend = time.time()
    runtime = usageend - usagestart
    print(f"Simulation {label} completed with a runtime of: {runtime:.2f} seconds")
    return runtime

def run_command(command, output_file="test.out"):
    with open(output_file, "w") as outfile:
        subprocess.run(command, shell=True, check=True, stdout=outfile, stderr=subprocess.STDOUT)

def render_input_file(basepath="./tmp/", filename="test", params={}, template_path="./input_templates/test.in"):
    # Use default params if insufficient input:
    tmp_params = default_params
    tmp_params.update(params)
    params = tmp_params

    # Define the directory and the filename for the run, to ensure good file management
    currentpath = basepath + f"{filename}/"
    os.makedirs(currentpath, exist_ok=True)

    # Write the correct settings into the template to prepare an input file
    env = j2.Environment(loader=j2.FileSystemLoader("."))
    template = env.get_template(template_path)
    output = template.render(params, outdir=currentpath, prefix=f"{filename}")
    with open(currentpath + f"{filename}.in", "w") as f:
        f.write(output)
    
    return f"{currentpath}{filename}.in"

def simulate_from_template(program="pw.x", basepath="./tmp/", filename="test", prefix="test", params={}, cpus=1, template_path="./input_templates/test.in"):
    """Runs a simulation using the selected program and by inputing a rendered inputfile from the template with added params"""
    
    # Use default params if insufficient input:
    tmp_params = default_params
    tmp_params.update(params)
    params = tmp_params
    # Define the directory and the filename for the run, to ensure good file management
    currentpath = basepath
    os.makedirs(currentpath, exist_ok=True)

    # Write the correct settings into the template to prepare an input file
    env = j2.Environment(loader=j2.FileSystemLoader("."), keep_trailing_newline=True)
    template = env.get_template(template_path)
    output = template.render(params, outdir=currentpath, prefix=prefix)
    with open(currentpath + f"{filename}.in", "w") as f:
        f.write(output)

    # Run the simulation
    run_logged_command(generate_command(cpus, program=program, input_path=currentpath + f"{filename}.in"), output_file=currentpath + f"{filename}.out", label=f"{filename}")

def simulate_from_template_logged(program="pw.x", basepath="./tmp/", filename="test", params={}, cpus=1, template_path="./input_templates/test.in"):
    """Runs a simulation using the selected program and by inputing a rendered input file from the template with the selected params. \n
    Logs results in an file under the basepath named "results.final" 
    """
    # Use default params if insufficient input:
    tmp_params = default_params
    tmp_params.update(params)
    params = tmp_params

    # Define the directory and the filename for the run, to ensure good file management
    currentpath = basepath + f"{filename}/"
    os.makedirs(currentpath, exist_ok=True)

    # Write the correct settings into the template to prepare an input file
    env = j2.Environment(loader=j2.FileSystemLoader("."))
    template = env.get_template(template_path)
    output = template.render(params, outdir=currentpath, prefix=f"{filename}")
    with open(currentpath + f"{filename}.in", "w") as f:
        f.write(output)

    # Run the simulation and log the runtime
    runtime = run_logged_command(generate_command(cpus, program=program, input_path=currentpath + f"{filename}.in"), output_file=currentpath + f"{filename}.out", label=f"{filename}")
    
    # Write the results to the batch output file
    outpath = currentpath + f"{filename}.out"
    with open(basepath + "results.final", "a") as outfile:
        outfile.write(f"{params['ecutwfc']};{params['k']};{params['celldm']};{cpus};{runtime};")
        with open(outpath, "r") as f:
            for line in f:
                if "!    total energy              =" in line:
                    outfile.write(f"{line[33:-4].strip()}\n")
                    return float(line[33:-4].strip())

def simulate_structure(structure : structure, program="pw.x", basepath="./tmp/", filename="test", prefix="test", params={}, cpus=1, template_path="./input_templates/standard.in"):
    params.update(structure.to_params())
    simulate_from_template(program=program, basepath=basepath, filename=filename, prefix=prefix, params=params, cpus=cpus, template_path=template_path)