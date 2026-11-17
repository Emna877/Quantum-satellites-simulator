// Cesium is a renderer for recorded ITRF positions, never an orbital propagator.
export class Globe {
 constructor(onSelect){
  this.onSelect=onSelect;this.layers={orbit:true,track:true,link:true,events:true,lighting:true};
  if(!globalThis.Cesium){document.querySelector('#globeUnavailable').hidden=false;return;}
  try{
   const C=Cesium;
   this.viewer=new C.Viewer('globe',{animation:false,timeline:false,baseLayerPicker:false,geocoder:false,
    homeButton:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,infoBox:false,
    selectionIndicator:true,shouldAnimate:false,baseLayer:false,terrainProvider:new C.EllipsoidTerrainProvider()});
   this.viewer.scene.backgroundColor=C.Color.fromCssColorString('#050a12');
   this.viewer.scene.globe.enableLighting=true;this.viewer.scene.globe.baseColor=C.Color.fromCssColorString('#18304b');
   this.viewer.clock.shouldAnimate=false;
   C.ArcGisMapServerImageryProvider.fromUrl('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer').then(provider=>this.viewer.imageryLayers.addImageryProvider(provider)).catch(()=>{document.dispatchEvent(new CustomEvent('console-info',{detail:'Earth imagery could not load. The globe uses a plain ellipsoid; recorded geometry is unchanged.'}));});
   this.viewer.screenSpaceEventHandler.setInputAction(click=>{const object=this.viewer.scene.pick(click.position);if(object?.id?.properties?.eventId)this.onSelect(object.id.properties.eventId.getValue());},C.ScreenSpaceEventType.LEFT_CLICK);
   this.viewer.selectedEntityChanged.addEventListener(entity=>{if(entity?.id==='ground-station')document.dispatchEvent(new CustomEvent('console-info',{detail:'Ground station selected. Range and elevation use the shared Orekit geometry.'}));});
   this.reset();
  }catch(error){document.querySelector('#globeUnavailable').hidden=false;document.dispatchEvent(new CustomEvent('console-info',{detail:'Cesium/WebGL could not initialize: '+error.message}));}
 }
 load(run){
  this.run=run;if(!this.viewer)return;
  const C=Cesium,v=this.viewer;v.entities.removeAll();this.events=[];
  const position=new C.SampledPositionProperty(C.ReferenceFrame.FIXED);
  for(const sample of run.telemetry)position.addSample(C.JulianDate.fromIso8601(sample.timestamp),new C.Cartesian3(...sample.position_m));
  position.setInterpolationOptions({interpolationDegree:1,interpolationAlgorithm:C.LinearApproximation});
  this.position=position;
  this.satellite=v.entities.add({id:'satellite',name:'Quantum CubeSat · recorded Orekit state',position,
   // Depth-tested so the Earth hides the satellite when it is on the far side.
   billboard:{image:'/console/satellite.svg',width:34,height:34,verticalOrigin:C.VerticalOrigin.CENTER},
   label:{text:'QUANTUM CUBESAT',font:'10px monospace',fillColor:C.Color.fromCssColorString('#8de9fb'),pixelOffset:new C.Cartesian2(0,-29),showBackground:true,backgroundColor:C.Color.fromCssColorString('#081726cc')},
   path:{show:true,width:1.8,leadTime:run.period_seconds||6000,trailTime:run.period_seconds||6000,resolution:30,material:new C.PolylineGlowMaterialProperty({glowPower:.12,color:C.Color.fromCssColorString('#57d8f5')})}});
  const track=run.telemetry.filter(p=>Number.isFinite(p.latitude_deg)&&Number.isFinite(p.longitude_deg)).map(p=>C.Cartesian3.fromDegrees(p.longitude_deg,p.latitude_deg,800));
  if(track.length>1)this.track=v.entities.add({id:'ground-track',polyline:{positions:track,width:1,arcType:C.ArcType.NONE,material:new C.PolylineDashMaterialProperty({color:C.Color.fromCssColorString('#5b91a799'),dashLength:8})}});
  if(run.station){this.stationPosition=C.Cartesian3.fromDegrees(run.station.lon_deg,run.station.lat_deg,run.station.alt_m||0);
   // The marker is drawn 3 km up so it does not flicker into the ground, while the Earth
   // still hides it when the station is on the far side. The link line uses the true position.
   const marker=C.Cartesian3.fromDegrees(run.station.lon_deg,run.station.lat_deg,(run.station.alt_m||0)+3000);
   this.station=v.entities.add({id:'ground-station',name:run.station.name,position:marker,
    point:{pixelSize:7,color:C.Color.fromCssColorString('#7be2c7'),outlineColor:C.Color.fromCssColorString('#102b2a'),outlineWidth:4},
    label:{text:run.station.name.replaceAll('_',' ').toUpperCase(),font:'10px monospace',fillColor:C.Color.fromCssColorString('#98d6c8'),pixelOffset:new C.Cartesian2(0,19)}});
   this.link=v.entities.add({id:'geometric-link',polyline:{positions:new C.CallbackProperty(time=>{const p=position.getValue(time);return p?[this.stationPosition,p]:[];},false),width:1.6,arcType:C.ArcType.NONE,material:C.Color.fromCssColorString('#69dfe8')}});
  }else{this.station=this.link=null;this.stationPosition=null;}
  for(const event of run.events.filter(e=>e.kind!=='contact')){
   const date=C.JulianDate.fromDate(new Date(event.startMs));const point=position.getValue(date);if(!point)continue;
   this.events.push(v.entities.add({id:event.id,name:event.label,position:event.kind==='disturbance'?position:point,properties:{eventId:event.id},
    availability:new C.TimeIntervalCollection([new C.TimeInterval({start:date,stop:C.JulianDate.fromDate(new Date(Math.min(run.endMs,Math.max(event.endMs,event.startMs+60000))))})]),
    point:{pixelSize:event.kind==='disturbance'?11:7,color:C.Color.fromCssColorString(event.kind==='disturbance'?'#f18687':event.kind==='prototype'?'#b69cfa':'#eab875'),outlineColor:C.Color.fromCssColorString('#162738'),outlineWidth:3},
    label:{text:event.kind==='disturbance'?'MODELED DISTURBANCE':event.kind==='prototype'?'PROTOTYPE MARKER':event.label,font:'8px monospace',fillColor:C.Color.fromCssColorString('#c5cbd4'),pixelOffset:new C.Cartesian2(0,18)}}));
  }
  v.clock.startTime=C.JulianDate.fromDate(new Date(run.startMs));v.clock.stopTime=C.JulianDate.fromDate(new Date(run.endMs));
  v.clock.currentTime=C.JulianDate.clone(v.clock.startTime);this.applyLayers();this.reset();
 }
 update(time,physical,metrics){if(!this.viewer)return;const C=Cesium;this.viewer.clock.currentTime=C.JulianDate.fromDate(new Date(time));if(this.link){this.link.show=this.layers.link&&Number.isFinite(physical?.elev_deg)&&physical.elev_deg>=(this.run.request.min_elevation_deg??5);this.link.polyline.material=C.Color.fromCssColorString(metrics?.rf?.available?'#5fd7db':'#e4ac61');}}
 follow(){if(this.viewer&&this.satellite)this.viewer.trackedEntity=this.satellite;}
 free(){if(this.viewer)this.viewer.trackedEntity=undefined;}
 reset(){if(!this.viewer)return;this.free();const C=Cesium;const lon=this.run?.station?.lon_deg??10.18,lat=this.run?.station?.lat_deg??23;this.viewer.camera.flyTo({destination:C.Cartesian3.fromDegrees(lon,lat-6,19000000),duration:.6});}
 setLayer(name,value){this.layers[name]=value;this.applyLayers();}
 applyLayers(){if(!this.viewer)return;if(this.satellite)this.satellite.path.show=this.layers.orbit;if(this.track)this.track.show=this.layers.track;if(this.link)this.link.show=this.layers.link;for(const event of this.events||[])event.show=this.layers.events;this.viewer.scene.globe.enableLighting=this.layers.lighting;}
 resize(){this.viewer?.resize();}
}
