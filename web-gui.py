#!/opt/local/bin/python

## For anything
from twisted.internet import reactor

## For WebSockets
try:
	## New style autobahn
	from autobahn.twisted.websocket import WebSocketServerFactory, WebSocketServerProtocol, listenWS
except ImportError:
	## Old style autobahn
	from autobahn.websocket import WebSocketServerFactory, WebSocketServerProtocol, listenWS

## All payloads are JSON-formatted.
import json
import src.parameters
from src.spline_computer import *
from src.tictoc import tic, toc, tictoc_dec
from itertools import izip as zip
from numpy import argmax

class WebGUIServerProtocol( WebSocketServerProtocol ):
	def connectionMade( self ):
		WebSocketServerProtocol.connectionMade( self )
		self.engine = self.factory.engine
		self.engine_type = 'ours'
		
		print 'CONNECTED'
	
	#@tictoc_dec
	def onMessage( self, msg, binary ):
		### BEGIN DEBUGGING
		if parameters.kVerbose >= 2:
			if not binary:
				from pprint import pprint
				space = msg.find( ' ' )
				if space == -1:
					print msg
				else:
					print msg[ :space ]
					pprint( json.loads( msg[ space+1 : ] ) )
		elif parameters.kVerbose >= 1:
			if not binary:
				print msg[:72] + ( ' ...' if len( msg ) > 72 else '' )
		### END DEBUGGING
		
		engine = self.engine
		
		if msg.startswith( 'set-engine-type ' ):
			engine_type = json.loads( msg[ len( 'set-engine-type ' ): ] )
			
			if self.engine_type == engine_type: return	
			self.factory.engine = self.engine = build_engine( engine_type, copy = engine )
			self.engine_type = engine_type
			
			if len( self.engine.handle_positions ) == 0: return
			
			self.engine.precompute_configuration()
			self.engine.prepare_to_solve()
			
			all_paths = self.engine.solve_transform_change()	
			all_positions = make_chain_from_control_groups( all_paths )
			self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
			self.retrieve_energy()
			
			return
			
			
		##################### Naive Approaches functions Begin ##########################
		if 'fourcontrols' == self.engine_type or 'twoendpoints' == self.engine_type or 'jacobian' == self.engine_type:
			if binary:
				print 'Received unknown message: binary of length', len( msg )
		
			elif msg.startswith( 'paths-info ' ):	   
				paths_info = json.loads( msg[ len( 'paths-info ' ): ] )
				try:
					boundary_index = argmax([ info['bbox_area'] for info in paths_info if info['closed'] ])
				except ValueError:
					boundary_index = -1
			
				self.engine.init_engine( paths_info, boundary_index )

		
			elif msg.startswith( 'handle-positions-and-transforms ' ):
				handles = json.loads( msg[ len( 'handle-positions-and-transforms ' ): ] )
			
				positions = [ pos for pos, transform in handles ]
				transforms = [ transform for pos, transform in handles ]
				self.engine.set_handle_positions( positions, transforms )
				## Stop here it if it's empty.
				if len( handles ) == 0: return
			
				self.engine.precompute_configuration()
				self.engine.prepare_to_solve()
				all_paths = self.engine.solve_transform_change()

				all_positions = make_chain_from_control_groups( all_paths )
				self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
				tic( 'compute_energy_and_distances' )
	 			self.retrieve_energy()
				toc()

				## Generate the triangulation and the BBW weights.
				# self.engine ...
		
			elif msg.startswith( 'handle-transforms ' ):
				handle_transforms = json.loads( msg[ len( 'handle-transforms ' ): ] )
			
				tic( 'transform_change' )
				for handle_index, handle_transform in handle_transforms:
					self.engine.transform_change( handle_index, handle_transform )
				toc()
			
				tic( 'engine.solve_transform_change()' )
				all_paths = self.engine.solve_transform_change()	
				toc()

				tic( 'make_chain_from_control_groups' )
				all_positions = make_chain_from_control_groups( all_paths )
				toc()
				self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )


				## Solve for the new curve positions given the updated transform matrix.
				# new_positions = engine ...
			
				## Send the new positions to the GUI.
				# self.sendMessage( 'paths-positions ' + json.dumps( new_positions ) )
		
			elif msg.startswith( 'control-point-constraint ' ):	pass	
			elif msg.startswith( 'set-weight-function ' ):
				weight_function = json.loads( msg[ len( 'set-weight-function ' ): ] )
			
				## Do nothing if this would do nothing.
				if self.engine.get_weight_function() == weight_function: return
			
				self.engine.set_weight_function( weight_function )
			
				try:
					self.engine.prepare_to_solve()
					all_paths = self.engine.solve_transform_change()
					all_positions = make_chain_from_control_groups( all_paths )
					self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
					self.retrieve_energy()
				
				except NoHandlesError:
					## No handles yet, so nothing to do.
					pass
				
			elif msg.startswith( 'enable-arc-length ' ):	pass
			elif msg.startswith( 'iterations ' ): 	pass	
			elif msg.startswith( 'handle-transform-drag-finished' ):
				self.retrieve_energy()
				
			else:
				print 'Received unknown message:', msg	
		##################### Naive Approaches functions End ##########################
		##################### YS Approaches functions Begin ##########################
		elif 'ours' == self.engine_type:
			if binary:
				print 'Received unknown message: binary of length', len( msg )
		
			elif msg.startswith( 'paths-info ' ):	   
				paths_info = json.loads( msg[ len( 'paths-info ' ): ] )
				try:
					boundary_index = argmax([ info['bbox_area'] for info in paths_info if info['closed'] ])
				except ValueError:
					boundary_index = -1
			
				self.engine.init_engine( paths_info, boundary_index )
				all_constraints = self.engine.all_constraints

				print_paths_info_stats( paths_info, all_constraints )
			
				for i, constraints in enumerate( all_constraints ):
					for j, constraint in enumerate( constraints ):
	
						continuity = constraint[0]
						fixed = constraint[1]
					
						payload = [ i, j, { 'fixed': fixed, 'continuity': continuity} ]
						self.sendMessage( 'control-point-constraint ' + json.dumps( payload ) )

		
			elif msg.startswith( 'handle-positions-and-transforms ' ):
				handles = json.loads( msg[ len( 'handle-positions-and-transforms ' ): ] )
			
				positions = [ pos for pos, transform in handles ]
				transforms = [ transform for pos, transform in handles ]
				self.engine.set_handle_positions( positions, transforms )
				## Stop here it if it's empty.
				if len( handles ) == 0: return
			
				self.engine.precompute_configuration()
				self.engine.prepare_to_solve()
				all_paths = self.engine.solve_transform_change()

				all_positions = make_chain_from_control_groups( all_paths )
				self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
				tic( 'compute_energy_and_distances' )
				self.retrieve_energy()
				toc()

				## Generate the triangulation and the BBW weights.
				# self.engine ...
		
			elif msg.startswith( 'handle-transforms ' ):
				handle_transforms = json.loads( msg[ len( 'handle-transforms ' ): ] )
			
				tic( 'transform_change' )
				for handle_index, handle_transform in handle_transforms:
					self.engine.transform_change( handle_index, handle_transform )
				toc()
			
				tic( 'engine.solve_transform_change()' )
				all_paths = self.engine.solve_transform_change()	
				toc()

				tic( 'make_chain_from_control_groups' )
				all_positions = make_chain_from_control_groups( all_paths )
				toc()
				self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )


				## Solve for the new curve positions given the updated transform matrix.
				# new_positions = engine ...
			
				## Send the new positions to the GUI.
				# self.sendMessage( 'paths-positions ' + json.dumps( new_positions ) )
		
			elif msg.startswith( 'control-point-constraint ' ):
				paths_info = json.loads( msg[ len( 'control-point-constraint ' ): ] )
			
				constraint = [None]*2
				constraint[0] = str( paths_info[2][ u'continuity' ] )
				constraint[1] = paths_info[2][ u'fixed' ]
			
				self.engine.constraint_change( paths_info[0], paths_info[1], constraint )
			
				try:
					self.engine.prepare_to_solve()
					all_paths = self.engine.solve_transform_change()
	
					all_positions = make_chain_from_control_groups( all_paths )
					self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
			
				except NoHandlesError:
					## No handles yet, so nothing to do.
					pass

				## Solve for the new curve positions given the updated control point constraint.
		
			elif msg.startswith( 'set-weight-function ' ):
				weight_function = json.loads( msg[ len( 'set-weight-function ' ): ] )
			
				## Do nothing if this would do nothing.
				if self.engine.get_weight_function() == weight_function: return
			
				self.engine.set_weight_function( weight_function )
			
				try:
					self.engine.prepare_to_solve()
					all_paths = self.engine.solve_transform_change()
					all_positions = make_chain_from_control_groups( all_paths )
					self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
					self.retrieve_energy()
				
				except NoHandlesError:
					## No handles yet, so nothing to do.
					pass
		
			elif msg.startswith( 'enable-arc-length ' ):
				enable_arc_length = json.loads( msg[ len( 'enable-arc-length ' ): ] )
			
				## Do nothing if this would do nothing.
				if self.engine.get_enable_arc_length() == enable_arc_length: return
			
				self.engine.set_enable_arc_length( enable_arc_length )
			
				try:
					self.engine.prepare_to_solve()
					all_paths = self.engine.solve_transform_change()
					# print 'returned results: ', all_paths
					all_positions = make_chain_from_control_groups( all_paths )
					self.sendMessage( 'paths-positions ' + json.dumps( all_positions ) )
					self.retrieve_energy()
				
				except NoHandlesError:
					## No handles yet, so nothing to do.
					pass
		
			elif msg.startswith( 'iterations ' ):
				iterations = json.loads( msg[ len( 'iterations ' ): ] )
				print 'multiple iterations:', iterations
				self.engine.set_iterations( iterations )
		
			elif msg.startswith( 'handle-transform-drag-finished' ):
			
				self.retrieve_energy()
			
			else:
				print 'Received unknown message:', msg
		##################### YS Approaches functions End ##########################

			
	def retrieve_energy( self )	:
		
		if parameters.kNoOverlays:	return
		
		try: 
			all_energy, target_curves, all_distances = self.engine.compute_energy_and_maximum_distance()
		
			energy_and_polyline = [
				[
					{ 'target-curve-polyline': points.tolist(), 'energy': energy, 'distance': distance }
					for energy, points, distance in zip( path_energy, path_points, path_distances )
				]
				for path_energy, path_points, path_distances in zip( all_energy, target_curves, all_distances )
				]
		
			if parameters.kVerbose >= 2:
				all_energy = asarray( all_energy )
				dists = asarray([ [ curve['maximum_distance'] for curve in path ] for path in all_distances ])
				print 'path_num: ', len( all_energy )
				print 'curve_num: ', sum( [len( curve_energy ) for curve_energy in all_energy] )
				print 'energy sum: ', sum( [sum( curve_energy ) for curve_energy in all_energy] )
				e_data = asarray( [ [ max( e ), min( e ), mean( e ) ] for e in all_energy ] ).T
				d_data = asarray( [ [ max( d ), min( d ), mean( d ) ] for d in dists ] ).T
# 				print 'energy:', max( e_data[0] ),  min( e_data[1] ), mean( e_data[2] )
				print 'distances:', max( d_data[0] )#,  min( d_data[1] ), mean( d_data[2] )
		
			if parameters.kComputeComparisonCurves:
				from FitCurves.FitCurves import FitCurve
				import itertools
			
				schneider_curves = []
				for spline in energy_and_polyline:
					schneider_curves.append( FitCurve( list( itertools.chain( *[ curve['target-curve-polyline'] for curve in spline ] ) ), 10 ).tolist() )
			
				#from pprint import pprint
				#pprint( schneider_curves )
				self.sendMessage( 'update-comparison-curve ' + json.dumps( schneider_curves ) )

			self.sendMessage( 'update-target-curve ' + json.dumps( energy_and_polyline ) )

		except NoHandlesError:
			## No handles yet, so nothing to do.
			pass


def make_chain_from_control_groups( all_paths ):
	
	all_positions = []	
	for path in all_paths:
		if len( path ) > 1:
			new_positions = concatenate( asarray(path)[:-1, :-1] )
			new_positions = concatenate( ( new_positions, path[-1] ) )
		else:
			new_positions = path[0]
		new_positions = new_positions.tolist()
		all_positions.append( new_positions )
		
	return all_positions

def print_paths_info_stats( paths_info, all_constraints ):
	print 'Opening a file with', len( paths_info ), 'paths.'
	curve_couts = [ ( len( path['cubic_bezier_chain'] ) - 1 ) / 3. for path in paths_info ]
	print 'A total of', sum( curve_couts ), 'cubic bezier curves.'
	print 'Longest number of curves in a path:', max( curve_couts )
	print 'Average number of curves in a path:', average( curve_couts )
	print 'Median number of curves in a path:', median( curve_couts )
	
	counts = {}
	for i, constraints in enumerate( all_constraints ):
		for j, constraint in enumerate( constraints ):
			
			continuity = constraint[0]
			counts.setdefault( continuity, 0 )
			counts[ continuity ] += 1
	
	print 'Constraint-type counts'
	for name in sorted( counts.iterkeys() ):
		print '%s: %s' % ( name, counts[ name ] )

class StubServerProtocol( WebSocketServerProtocol ):
	def connectionMade( self ):
		WebSocketServerProtocol.connectionMade( self )
		print 'CONNECTED'
	
	@tictoc_dec
	def onMessage( self, msg, binary ):
		if binary:
			print 'Received unknown message: binary of length', len( msg )
		else:
			from pprint import pprint
			space = msg.find( ' ' )
			if space == -1:
				print msg
			else:
				print msg[ :space ]
				pprint( json.loads( msg[ space+1 : ] ) )
				

def setupWebSocket( address, engine, protocol ):
	'''
	Listen for WebSocket connections at the given address.
	'''
	
	factory = WebSocketServerFactory( address )
	factory.engine = engine
	factory.protocol = protocol
	listenWS( factory )
	
	print "Listening for WebSocket connections at:", address

def build_engine( type = 'ours', copy = None ):
	engine = None
	
# 	if parameters.EngineType['YSApproach'] == parameters.kEngineType:	
# 		engine = YSEngine()
# 	elif parameters.EngineType['FourControls'] == parameters.kEngineType:	
# 		engine = FourControlsEngine()
# 	elif parameters.EngineType['TwoEndpoints'] == parameters.kEngineType:	
# 		engine = TwoEndpointsEngine()
# 	elif parameters.EngineType['Jacobian'] == parameters.kEngineType:	
# 		engine = JacobianEngine()
# 	else: 
# 		raise RuntimeError("Unknown engine selected.")
	if 'ours' == type:
		engine = YSEngine()
	elif 'fourcontrols' == type:
		engine = FourControlsEngine()
	elif 'twoendpoints' == type:
		engine = TwoEndpointsEngine()
	elif 'jacobian' == type:
		engine = JacobianEngine()
	else:
		raise RuntimeError("Unknown engine selected.")
	
	if copy is not None:
		engine.copy_engine( copy )
	
	return engine
	
def main():
	import os, sys
	
	if 'verbose' in sys.argv[1:]:
		parameters.kVerbose = int( sys.argv[ sys.argv.index( 'verbose' ) + 1 ] )
	
	print 'Verbosity level:', parameters.kVerbose
	
	protocol = WebGUIServerProtocol
	if 'stub' in sys.argv[1:]:
		print 'Stub only!'
		protocol = StubServerProtocol
	
	## Create engine:
	# engine = ...
	engine = build_engine()

	setupWebSocket( "ws://localhost:9123", engine, protocol )
	
	## Maybe you find this convenient
	if 'open' in sys.argv[1:]:
		os.system( 'open web-gui.html' )
	
	reactor.run()

if __name__ == '__main__': main()
