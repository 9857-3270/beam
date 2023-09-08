version = 0.075

# CONFIG
simulator = False
my_beamline = 'K13'
visible_points_limit = 14400 # a number of points visible simultaneously. Should be large (~3600 for 2 hours view)
seconds_limit = 300 # if a number of points is more than seconds_limit, seconds are not shown on time scale

# SIBIR-2 beam monitor
# v0.075
# - new label for shutter: open/close. Turns green if open, otherwise same color as everything else.
# - auto-rescale bug fixed (?)
# - MORE button
# - better STATUS parcer
# - Font size depends on window size
# - Database re-connection in case of SQL fail
# - better Colors
# TODO:
# - disable view re-calculation if the graph is scrolled by user
# - redraw BIG LABELZ on rescale
# - Integration with STM EXAFS & RTMT
# - Additional graphs&meters:
#	 - energy
#	 - lifetime
# FUTURE:
#	 SIBIR-1 monitor
#	 Windows tray mode
#	 Telegram notifier

import pyodbc as db
import time
import sys
import pyqtgraph as pg

from datetime import datetime

if simulator:
	import numpy

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

# BACKEND - REAL

class sib2BeamWorker(QObject):
	def __init__(self, beamline):
		self.beamline = beamline + '_on'
		self.beamline_request = "SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]=" +"'" + self.beamline + "'" + " order by [Time] desc"
		super().__init__()
		#self.status_dict = {53: 'experiment', 45: 'experiment', 37: 'experiment', 29: 'experiment', 51: 'injection', 52: 'acceleration', 15: 'service', 13: 'service', 11: 'service', 21: 'service', 19: 'injection', 20: 'injection', 27: 'injection', 35: 'injection',  -1 : 'no access'}
		self.connect()
		
	def connect(self):
		self.cnxn = db.connect('DRIVER={SQL Server};SERVER=10.10.0.24;DATABASE=Sib2_RF_ADC;UID=user;PWD=user')
		self.cursor = self.cnxn.cursor()
		#return cnxn, cursor

	def stat_parser(self, stat):
		stat = int(stat)
		det = stat % 8
		if det == 5:
			res = 'experiment'
		elif det == 4:
			res = 'acceleration'
		elif det == 3:
			res = 'injection'
		elif det == 7:
			res = 'service'
		else:
			res = 'unknown'
		return res
		
	def get_current(self):
		try:
			self.cursor.execute("SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]='Ibeam_S2_c' order by [Time] desc")
		except:
			print('Sib2BeamWorker error: Current value not found in database')
			return -1
		else:
			row = self.cursor.fetchone() # returns last row in selection. Use 'fetchmany' for many rows.
			if row:
				return row[0] #each row is a tuple of (I_Value, Time). So, row[o] is an I_Value
			else:
				return -1
	def get_status(self):
		try:
			self.cursor.execute("SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]='Status_S2' order by [Time] desc")
		except:
			print('Sib2BeamWorker error: Status_S2 value not found in database')
			return -1
		else:
			row = self.cursor.fetchone()
			if row:
				status_code = row[0]
			else:
				status_code =  -1
			print('Sibir 2 status code:', status_code)
			if status_code != -1:
				return self.stat_parser(status_code)
			else:
				return('unknown')
				
	def get_shutter(self, some_beamline):
		beamline_request = "SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]=" +"'" + some_beamline + "'" + " order by [Time] desc"
		try:
			self.cursor.execute(self.beamline_request)
		except:
			print('Sib2BeamWorker error: Beamline shutter position not found in database')
			return -1
		else:
			row = self.cursor.fetchone()
			if row:
				shutter = row[0] #2 is open, 1 is closed
			else:
				shutter =  -1
			#print(some_beamline, ': ', shutter)
			return(shutter)
	
	def get_energy(self):
		try:
			self.cursor.execute("SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]='EnergySib2' order by [Time] desc")
		except:
			print('Sib2BeamWorker error: SIBIR-2 Energy value not found in database')
			return -1
		else:
			row = self.cursor.fetchone() # returns last row in selection. Use 'fetchmany' for many rows.
			if row:
				return row[0]
			else:
				return -1
	
	def get_lifetime(self):
		try:
			self.cursor.execute("SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]='TAU_S2_c' order by [Time] desc")
		except:
			print('Sib2BeamWorker error: Lifetime (TAU) value not found in database')
			return -1
		else:
			row = self.cursor.fetchone() 
			if row:
				return row[0] #each row is a tuple of (I_Value, Time). So, row[o] is an I_Value
			else:
				return -1

class beamCurrentThread(QThread): # QThread wrapper for get_sibir2_current()
	updateBeamCurrent = pyqtSignal(float)
	updateStatus = pyqtSignal(str)
	updateShutter = pyqtSignal(bool)
	updateEnergy = pyqtSignal(float)
	updateLifetime = pyqtSignal(float)
	def __init__(self, worker):
		QThread.__init__(self)
		self.worker = worker
	def __del__(self):
		self.wait()
	def stop(self):
		self.running = False
	def run(self):
		self.running = True
		while self.running:
			try:
				current = self.worker.get_current()
				status = self.worker.get_status()
				#print('pau')
				if not simulator:
					shutter = self.worker.get_shutter(self.worker.beamline)
					#print('gav gav')
				else:
					shutter = 1
					#print('gov gov')
				#print('pau')
				energy = self.worker.get_energy()
				#print('paupau')
				lifetime = self.worker.get_lifetime()
				#print('paupaupau')
				if shutter > 1:
					shutter = True
				else:
					shutter = False
				#print('chikibamboni')
				#print(current, status, shutter, energy, lifetime)
			except:
				print('Error! No connection to database! Trying to reconnect...')
				self.worker.connect()
				time.sleep(5)
			else:
				if -1 not in (current, status, shutter, energy, lifetime):
					self.updateBeamCurrent.emit(current)
					print('SIBIR-2 current is:', current, 'mA')
					self.updateStatus.emit(status)
					print('SIBIR-2 status is:', status)
					self.updateShutter.emit(shutter)
					self.updateEnergy.emit(energy)
					print('SIBIR-2 energy is:', energy, 'MeV')
					self.updateLifetime.emit(lifetime)
					print('SIBIR-2 lifetime is:', lifetime, 's.')
				else:
					print('Error! No connection to database! Trying to reconnect...')
					self.worker.connect()
					time.sleep(5)
				t = datetime.now()
				t = t.strftime('%H:%M:%S')
				print(t)
			time.sleep(2)
		print('beamCurrentThread stopped!')

# BACKEND - SIMULATOR

class fakeBeamGenerator(QThread):
	def __init__(self):
		QThread.__init__(self)
		self.current = 0
	def __del__(self):
		self.wait()
	def stop(self):
		self.running = False
	def run(self):
		self.x = 0
		self.running = True
		while self.running:
			rnd = numpy.random.randint(2)
			if rnd == 1:
				self.x += 1
			else:
				self.x -= 1
			self.current = round(abs(self.x) * 0.01, 2)
			time.sleep(0.001)
			#print(rnd, self.current)

class fakeBeamWorker(QObject):
	def __init__(self, beamGen):
		super().__init__()
		self.beamGen = beamGen
		self.beamGen.start()
		self.beamline = 'К777'
	def get_current(self):
		#print('gagaga')
		return self.beamGen.current
	def get_status(self):
		#print('gugugu')
		return 'simulation'
	def get_shutter(self, beamline_alpha):
		return 1
	def get_energy(self):
		#print('gegege')
		return 8000
	def get_lifetime(self):
		#print('gigigi')
		return 10000
	def connect(self):
		pass


# FRONTEND

largeFont = QFont()
largeFont.setPointSize(144)
largeFont.setBold(True)

statFont = QFont()
statFont.setPointSize(72)
statFont.setBold(True)

def timestamp():
	return int(time.mktime(datetime.now().timetuple()))


class timeAxisItem(pg.AxisItem):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.showSeconds = True
		self.setLabel(text='Time', units=None)
		self.enableAutoSIPrefix(False)
	def tickStrings(self, values, scale, spacing):
		if self.showSeconds:
			return [datetime.fromtimestamp(value).strftime("%H:%M:%S") for value in values]
		else:
			return [datetime.fromtimestamp(value).strftime("%H:%M") for value in values]

class beamCurrentWindow(QWidget):
	def __init__(self):
		super().__init__()
		self.color_dict ={"experiment": "c", "injection":"r", "acceleration": "y", "simulation":"d"}
		self.status = 'unknown'
		self.shutter = False
		self.shutter_color = 'd'
		self.initUI()
		self.i = 0
	def setStatus(self, status):
		self.status = status
	def setShutter(self, shutter):
		self.shutter = shutter
		if shutter:
			self.shutLabel.setText('Beam: open')
		else:
			self.shutLabel.setText('Beam: closed')
	def showCurrent(self, current):
		#update the curve
		self.ys.append(current)
		self.xs.append(timestamp())
		if len(self.xs) > seconds_limit:
			self.dummyTimeAxis.showSeconds = False
		self.curve.setData(self.xs, self.ys)
		if len(self.xs) > visible_points_limit:
			self.graph.setXRange(self.xs[-visible_points_limit], self.xs[-1])
		else:
			#self.graph.setLimits(xMin = self.xs[0], xMax = self.xs[-1])
			self.graph.setXRange(self.xs[0], self.xs[-1])
		
		# show CURRENT and STATUS labels
		self.graph.removeItem(self.mA)
		self.graph.removeItem(self.statLabel)
		self.graph.removeItem(self.shutLabel)
		xrange, yrange = self.graph.viewRange()
		self.mA.setText(str(current) + ' mA')
		self.mA.setPos(xrange[0], yrange[0])
		self.graph.addItem(self.mA)
		
		self.shutLabel.setPos(xrange[0], yrange[1])
		self.graph.addItem(self.shutLabel)
		
		#some tricks to get the size of CURRENT label
		view_box = self.graph.getViewBox()
		br = self.mA.boundingRect()
		sx, sy = view_box.viewPixelSize()
		x_size = sx * br.width()
		y_size = sy * br.height()
		
		self.mA.setPos(self.mA.x(), self.mA.y() + y_size * 0.25)
		
		self.statLabel.setText(self.status)
		self.graph.addItem(self.statLabel)
		self.statLabel.setPos(self.mA.x(), self.mA.y() - y_size * 0.75)
		
		# show SHUTTER label
		self.shutLabel.setPos(self.shutLabel.x(), self.shutLabel.y() + y_size * 0.3)
		
		#set colors
		if self.status in self.color_dict:
			new_color = self.color_dict[self.status]
		else:
			new_color = "d" # d stands for grey ("dull"?)
		self.setAllColors(new_color)
		
	def setAllColors(self, color):
		self.mA.setColor(color)
		self.statLabel.setColor(color)
		self.curve.setPen(pg.mkPen(color, width = 4))
		if self.shutter:
			self.shutLabel.setColor("g")
		else:
			self.shutLabel.setColor(color)
		
	def createGraph(self):
		# AXIS LABELS
		self.currentAxis = pg.AxisItem(orientation='left')
		self.currentAxis.setLabel(text = 'I, mA')
		self.dummyTimeAxis = timeAxisItem(orientation='bottom')
		# CREATE GRAPH
		graph = pg.PlotWidget(axisItems = {'left': self.currentAxis, 'bottom': self.dummyTimeAxis})
		graph.showGrid(True, True, 0.5)
		graph.showButtons()
		graph.setMouseEnabled(x = True, y = False)
		# DATA OBJECTS
		self.xs = []
		self.ys = []
		# mA LABEL
		self.mA = pg.TextItem('--- mA', color = 'r')
		self.mA.setFont(largeFont)
		# Stat LABEL
		self.statLabel = pg.TextItem('experiment', color = 'r')
		self.statLabel.setFont(statFont)
		# Shut LABEL
		self.shutLabel = pg.TextItem('Beam: closed', color = 'r')
		self.shutLabel.setFont(statFont)
		return graph
	def initGraph(self): #creating a curve and adding to graph
		self.xs.clear()
		self.ys.clear()
		color = 'r' #red
		curve = pg.PlotDataItem(pen = pg.mkPen(color, width = 4))
		self.graph.addItem(curve)
		self.i = 0
		return curve
	def resizeEvent(self, event):
		new_size = event.size()
		h = new_size.height()
		
		largeFont.setPointSize(h // 9)
		largeFont.setBold(True)
		statFont.setPointSize(h // 20)
		statFont.setBold(True)
		
		self.mA.setFont(largeFont)
		self.statLabel.setFont(statFont)
		self.shutLabel.setFont(statFont)
		
		
	def initUI(self):
		mainLayout = QVBoxLayout()
		
		self.graph = self.createGraph()
		self.curve = self.initGraph()
		mainLayout.addWidget(self.graph)
		
		self.moreButton = QPushButton('More...')
		#self.moreButton.setAlignment(Qt.AlignRight)
		self.moreButton.setParent(self.graph)
		
		self.setLayout(mainLayout)
		self.setWindowTitle('SIBIR-2 beam monitor v.' + str(version))
		#geo = self.geometry()
		#self.setGeometry(geo.x(), geo.y(), 700, geo.height())
		#self.setMinimumSize(self.size())

# MAIN

if __name__ == "__main__":
	
	#request = "SELECT [I_Value],[Time] FROM Sib2_RF_ADC.dbo.Logic_ADC_view WHERE [Logic_Name]=" +"'" + my_beamline + "'" + " order by [Time] desc"
	#print(request)
	
	app = QApplication(sys.argv)
	
	bcw = beamCurrentWindow()
	bcw.show()
	
	# GEOMETRY - works properly only after show()
	geo = bcw.geometry()
	bcw.setGeometry(geo.x(), geo.y(), 350, geo.height())
	bcw.setMinimumSize(350, geo.height())
	
	# THREADS
	
	if simulator:
		fbg = fakeBeamGenerator()
		bc_worker = fakeBeamWorker(fbg)
	else:
		bc_worker = sib2BeamWorker(my_beamline)
	
	bct = beamCurrentThread(bc_worker)
	
	# CONNECTIONS
	bct.updateBeamCurrent.connect(bcw.showCurrent)
	bct.updateStatus.connect(bcw.setStatus)
	bct.updateShutter.connect(bcw.setShutter)
	
	bct.start()
	app.exec()
	sys.exit()