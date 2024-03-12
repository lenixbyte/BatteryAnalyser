from flask import Flask, jsonify, render_template, request, send_file
import random
import barcode
from barcode.writer import ImageWriter
from impedance import preprocessing
import json
from PIL import Image, ImageDraw
from impedance.models.circuits import CustomCircuit
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from impedance.visualization import plot_nyquist
import os

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload-battery-info', methods=['POST'])
def upload():
    data_keys = ['cell_condition', 'manufacturer', 'model', 'type', 'form_factor', 'mass_g', 'height_mm', 'diameter_mm', 'volume_cm3', 'nominal_voltage_V', 'nominal_energy_Wh', 'nominal_charge_capacity_Ah', 'voltage_range_V', 'current_continuous_A', 'peak_discharge_current_A', 'power_continuous_W', 'power_peak_W', 'energy_density_galvanmetric_Wh_kg', 'energy_density_volumetric_Wh_L', 'power_density_galvanmetric_W_kg', 'power_density_volumetric_W_L']
    form_data = request.form
    for key in data_keys:
        if key not in data_keys:
            return jsonify({'message': 'Missing field: '+key, 'success': False})

    if 'file' not in request.files:
        return render_template('index.html', message='No file part', success=False)
    
    file = request.files['file']
    file.filename = 'battery.jpg'
    
    if file.filename == '':
        return render_template('index.html', message='No selected file', success=False)

    if file:
        cell_id= str(random.randint(100000000000, 999999999999))
        EAN = barcode.get_barcode_class('ean13')
        ean = EAN(cell_id, writer=ImageWriter())
        ean.default_writer_options['module_height'] = 5.0
        ean.default_writer_options['write_text'] = False
        
        parameters_data = [
            {"name": "Rb", "value": "", "unit": "Ohm", "explanation": "Electrolyte resistance", "source": ""},
            {"name": "R_SEI", "value": "", "unit": "Ohm", "explanation": "Resistance due to SEI layer", "source": ""},
            {"name": "CPE_SEI", "value": "", "unit": "F", "explanation": "Capacitance due to SEI layer", "source": ""},
            {"name": "R_CT", "value": "", "unit": "Ohm", "explanation": "charge-transfer resistance that models the voltage drop over the electrode–electrolyte interface due to a load", "source": ""},
            {"name": "Wo1", "value": "", "unit": "", "explanation": "Frequency-dependent Warburg impedance models diffusion of lithium ions in the electrodes", "source": ""},
            {"name": "CPE_DL", "value": "", "unit": "F", "explanation": "Double-layer capacitance that models the effect of charges building up in the electrolyte at the electrode surface", "source": ""}
        ]

        os.makedirs('static/battery/'+cell_id)
        file.save('static/battery/'+cell_id +'/'+ file.filename)
        ean.save('static/battery/'+cell_id +'/'+ 'barcode')
        with open('data.json', 'r') as f:
            data = f.read()
            data = json.loads(data)
            data.append({'cell_id': cell_id, 'image': 'battery/'+cell_id+'/'+file.filename, 'barcode': 'battery/'+cell_id+'/barcode.png', 'data': form_data, 'csv': None, 'circuit': None, 'parameters': parameters_data})
        with open('data.json', 'w') as f:
            f.write(json.dumps(data))

    image = 'battery/'+cell_id+'/'+file.filename
    return render_template('index.html', message='File successfully uploaded!', image = image, success=True, barcode = 'battery/'+cell_id+'/barcode.png')

@app.route('/all_batteries')
def all_batteries():
    with open('data.json', 'r') as f:
        data = f.read()
        data = json.loads(data)
        print(data)
    return render_template('all_batteries.html', cells=data)

@app.route('/battery/<cell_id>')
def get_a_battery(cell_id, report_generated = False, message = None):
    with open('data.json', 'r') as f:
        data = f.read()
        data = json.loads(data)
        # circuits = "['R0', 'R1', 'C1', 'R2', 'Wo1', 'C2']"
        for cell in data:
            if cell['cell_id'] == cell_id:
                return render_template('battery.html', cell=cell, report_generated=report_generated, message=message)
        return render_template('battery.html', cell=None)
    
@app.route('/battery/generate_report', methods=['POST'])
def generate_report_from_csv():
    try:
        if 'cell_id' not in request.form:
            return jsonify({'message': 'Missing field: cell_id', 'success': False})
        cell_id = request.form['cell_id']
        if 'file' not in request.files:
            return render_template('battery.html', message='No file part', success=False)
        
        file = request.files['file']
        file.filename = 'battery.csv'
        
        if file.filename == '':
            return render_template('battery.html', message='No selected file', success=False)

        if file:
            frequencies, Z = preprocessing.readCSV(file)
            frequencies, Z = preprocessing.ignoreBelowX(frequencies, Z)
            

            circuit = 'R0-p(R1,C1)-p(R2-Wo1,C2)'
            initial_guess = [.01, .01, 100, .01, .05, 100, 1]

            circuit = CustomCircuit(circuit, initial_guess=initial_guess)
            
            circuit.fit(frequencies, Z)
            
            cicuitPath = 'static/battery/'+cell_id+'/circuit.png'  
            template = 'static/circuit_template.png'
            img = Image.open(template)
            r0 = circuit.parameters_[0]
            r1 = circuit.parameters_[1]
            c1 = circuit.parameters_[2]
            r2 = circuit.parameters_[3]
            wo1 = circuit.parameters_[4]
            c2 = circuit.parameters_[5]
            img.draw = ImageDraw.Draw(img)
            img.draw.text((99, 110), "R0: "+str(r0)+'[Ohm]', fill="black")
            img.draw.text((310, 200), "R1: "+str(r1)+'[Ohm]', fill="black")
            img.draw.text((290, 14), "C1: "+str(c1)+'[F]', fill="black")
            img.draw.text((566, 200), "R2: "+str(r2)+'[Ohm]', fill="black")
            img.draw.text((748, 200), "Wo1: "+str(wo1), fill="black")
            img.draw.text((630, 14), "C2: "+str(c2)+'[F]', fill="black")
            
            img.save(cicuitPath)
            
            Z_fit = circuit.predict(frequencies)
            fig, ax = plt.subplots()
            plot_nyquist(Z, fmt='o', scale=10, ax=ax)
            plot_nyquist(Z_fit, fmt='-', scale=10, ax=ax)
            
            plt.legend(['Data', 'Fit'])
            plt.gcf().set_size_inches(15, 7)
            if not os.path.exists('static/battery/'+cell_id +'/plots'):
                os.makedirs('static/battery/'+cell_id +'/plots')
            plt.savefig('static/battery/'+cell_id+'/plots/nyquist.png')
            
            file.save('static/battery/'+cell_id +'/'+ file.filename)
            with open('data.json', 'r') as f:
                data = f.read()
                data = json.loads(data)
                for cell in data:
                    if cell['cell_id'] == cell_id:
                        cell['csv'] = 'battery/'+cell_id+'/battery.csv'
                        cell['circuit'] = 'battery/'+cell_id+'/circuit.png'
                        cell['plot'] = 'battery/'+cell_id+'/plots/nyquist.png'
                        cell['parameters'][0]['value'] = r0
                        cell['parameters'][1]['value'] = r1
                        cell['parameters'][2]['value'] = c1
                        cell['parameters'][3]['value'] = r2
                        cell['parameters'][4]['value'] = wo1
                        cell['parameters'][5]['value'] = c2
                        cell['parameters'][0]['unit'] = 'Ohm'
                        cell['parameters'][1]['unit'] = 'Ohm'
                        cell['parameters'][2]['unit'] = 'F'
                        cell['parameters'][3]['unit'] = 'Ohm'
                        cell['parameters'][5]['unit'] = 'F'
                with open('data.json', 'w') as f:
                    f.write(json.dumps(data))
        return get_a_battery(cell_id, message='File successfully uploaded!', report_generated=True)
    except Exception as e:
        print(str(e))
        return render_template('battery.html', message='Error: '+str(e), success=False)
    

# /circuit-image.png?circuit=R0-p(R1,C1)-p(R2-Wo1,C2)&initial_guess=0.01,0.01,100,0.01,0.05,100,1

if __name__ == '__main__':
    app.run(debug=True, port = 5000)