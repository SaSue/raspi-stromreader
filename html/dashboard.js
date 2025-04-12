// dashboard.js

function formatDatum(date) {
  return date.toISOString().split("T")[0];
}

function berechneVerbrauch(daten) {
  if (daten.length < 2) return 0;
  return +(daten[daten.length - 1].bezug - daten[0].bezug).toFixed(2);
}

function aktualisiereAnzeige(aktuell) {
  document.getElementById("leistung").textContent = `${aktuell.leistung} W`;
  document.getElementById("bezug").textContent = `${aktuell.bezug.toFixed(2)} kWh`;
  document.getElementById("einspeisung").textContent = `${aktuell.einspeisung.toFixed(2)} kWh`;
}

function renderGauge(wert) {
  const ctx = document.getElementById("gauge").getContext("2d");
  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["", ""],
      datasets: [{
        data: [wert, 5000 - wert],
        backgroundColor: ["#fffb00", "#444"],
        borderWidth: 0
      }]
    },
    options: {
      cutout: "80%",
      rotation: -90,
      circumference: 180,
      plugins: { legend: { display: false } }
    }
  });
}

function renderVerlauf(daten) {
  const labels = daten.map(e => new Date(e.timestamp).toLocaleTimeString());
  const werte = daten.map(e => e.leistung);
  new Chart(document.getElementById("verlauf"), {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Leistung [W]",
        data: werte,
        borderColor: "#00aaff",
        fill: false
      }]
    },
    options: { scales: { x: { ticks: { autoSkip: true, maxTicksLimit: 10 } } } }
  });
}

(async () => {
  const heute = new Date();
  const gestern = new Date();
  gestern.setDate(heute.getDate() - 1);
  const heuteStr = formatDatum(heute);
  const gesternStr = formatDatum(gestern);

  const ladeTag = async (tag) => {
    try {
      const res = await fetch(`/history/${tag}.json`);
      if (!res.ok) throw new Error("Nicht gefunden");
      return await res.json();
    } catch {
      return [];
    }
  };

  const datenHeute = await ladeTag(heuteStr);
  const datenGestern = await ladeTag(gesternStr);

  if (datenHeute.length) {
    const aktuell = datenHeute[datenHeute.length - 1];
    aktualisiereAnzeige(aktuell);
    renderGauge(aktuell.leistung);
    renderVerlauf(datenHeute);
  } else {
    document.getElementById("leistung").textContent = "Keine Daten vorhanden";
    document.getElementById("bezug").textContent = "Keine Daten vorhanden";
    document.getElementById("einspeisung").textContent = "Keine Daten vorhanden";
  }

  document.getElementById("verbrauchHeute").textContent = datenHeute.length ? `${berechneVerbrauch(datenHeute)} kWh` : "Keine Daten vorhanden";
  document.getElementById("verbrauchGestern").textContent = datenGestern.length ? `${berechneVerbrauch(datenGestern)} kWh` : "Keine Daten vorhanden";

  const tage = [];
  const werte = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const tag = formatDatum(d);
    try {
      const data = await ladeTag(tag);
      tage.push(tag);
      werte.push(berechneVerbrauch(data));
    } catch {
      tage.push(tag);
      werte.push(0);
    }
  }

  new Chart(document.getElementById("woche"), {
    type: "bar",
    data: {
      labels: tage,
      datasets: [{
        label: "Tagesverbrauch [kWh]",
        data: werte,
        backgroundColor: "#00aaff"
      }]
    }
  });
})();

fetch('/strom.json')
  .then(res => res.json())
  .then(data => {
    const updateElem = document.getElementById('last-update-text');
    if (data.timestamp) {
      const time = new Date(data.timestamp);
      const formatted = time.toLocaleString(undefined, {
        dateStyle: 'short',
        timeStyle: 'medium'
      });
      updateElem.textContent = `Letzte Aktualisierung: ${formatted}`;
    } else {
      updateElem.textContent = 'Letzte Aktualisierung: unbekannt';
    }
    if (data.seriennummer) {
        snElem.textContent = `Seriennummer: ${data.seriennummer}`;
    } else {
        snElem.textContent = 'Seriennummer: unbekannt';
    }    
  })
  .catch(() => {
    document.getElementById('last-update-text').textContent = 'Letzte Aktualisierung: Fehler beim Laden';
  });