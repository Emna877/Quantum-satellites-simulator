console.log('Frontend main.js starting');
fetch('/api/sat/orbit')
  .then(r => r.json())
  .then(czml => console.log('Received CZML', czml))
  .catch(err => console.warn('Could not fetch CZML (running locally?)', err));
