/**
 * Bundled city-coordinate gazetteer for Indian cities.
 *
 * These coordinates are real geographic locations used only to place a city
 * that already exists in the uploaded dataset.  A city absent from this list is
 * never guessed: it is reported in the fallback table instead.
 */

export type CityCoordinate = { lat: number; lon: number; state?: string };

export const CITY_COORDINATES: Record<string, CityCoordinate> = {
  // Gujarat
  ahmedabad: { lat: 23.0225, lon: 72.5714, state: "Gujarat" },
  gandhinagar: { lat: 23.2156, lon: 72.6369, state: "Gujarat" },
  surat: { lat: 21.1702, lon: 72.8311, state: "Gujarat" },
  vadodara: { lat: 22.3072, lon: 73.1812, state: "Gujarat" },
  baroda: { lat: 22.3072, lon: 73.1812, state: "Gujarat" },
  rajkot: { lat: 22.3039, lon: 70.8022, state: "Gujarat" },
  vapi: { lat: 20.3893, lon: 72.9106, state: "Gujarat" },
  valsad: { lat: 20.5992, lon: 72.9342, state: "Gujarat" },
  bhavnagar: { lat: 21.7645, lon: 72.1519, state: "Gujarat" },
  jamnagar: { lat: 22.4707, lon: 70.0577, state: "Gujarat" },
  junagadh: { lat: 21.5222, lon: 70.4579, state: "Gujarat" },
  anand: { lat: 22.5645, lon: 72.9289, state: "Gujarat" },
  navsari: { lat: 20.9467, lon: 72.9520, state: "Gujarat" },
  bharuch: { lat: 21.7051, lon: 72.9959, state: "Gujarat" },

  // Maharashtra
  mumbai: { lat: 19.0760, lon: 72.8777, state: "Maharashtra" },
  bombay: { lat: 19.0760, lon: 72.8777, state: "Maharashtra" },
  "navi mumbai": { lat: 19.0330, lon: 73.0297, state: "Maharashtra" },
  thane: { lat: 19.2183, lon: 72.9781, state: "Maharashtra" },
  pune: { lat: 18.5204, lon: 73.8567, state: "Maharashtra" },
  poona: { lat: 18.5204, lon: 73.8567, state: "Maharashtra" },
  nashik: { lat: 19.9975, lon: 73.7898, state: "Maharashtra" },
  nagpur: { lat: 21.1458, lon: 79.0882, state: "Maharashtra" },
  aurangabad: { lat: 19.8762, lon: 75.3433, state: "Maharashtra" },
  solapur: { lat: 17.6599, lon: 75.9064, state: "Maharashtra" },
  kolhapur: { lat: 16.7050, lon: 74.2433, state: "Maharashtra" },

  // Delhi NCR
  delhi: { lat: 28.6139, lon: 77.2090, state: "Delhi" },
  "new delhi": { lat: 28.6139, lon: 77.2090, state: "Delhi" },
  gurugram: { lat: 28.4595, lon: 77.0266, state: "Haryana" },
  gurgaon: { lat: 28.4595, lon: 77.0266, state: "Haryana" },
  noida: { lat: 28.5355, lon: 77.3910, state: "Uttar Pradesh" },
  faridabad: { lat: 28.4089, lon: 77.3178, state: "Haryana" },
  ghaziabad: { lat: 28.6692, lon: 77.4538, state: "Uttar Pradesh" },

  // Karnataka
  bengaluru: { lat: 12.9716, lon: 77.5946, state: "Karnataka" },
  bangalore: { lat: 12.9716, lon: 77.5946, state: "Karnataka" },
  mysuru: { lat: 12.2958, lon: 76.6394, state: "Karnataka" },
  mysore: { lat: 12.2958, lon: 76.6394, state: "Karnataka" },
  mangaluru: { lat: 12.9141, lon: 74.8560, state: "Karnataka" },
  mangalore: { lat: 12.9141, lon: 74.8560, state: "Karnataka" },
  hubballi: { lat: 15.3647, lon: 75.1240, state: "Karnataka" },
  hubli: { lat: 15.3647, lon: 75.1240, state: "Karnataka" },
  belagavi: { lat: 15.8497, lon: 74.4977, state: "Karnataka" },

  // Telangana / Andhra Pradesh
  hyderabad: { lat: 17.3850, lon: 78.4867, state: "Telangana" },
  warangal: { lat: 17.9689, lon: 79.5941, state: "Telangana" },
  visakhapatnam: { lat: 17.6868, lon: 83.2185, state: "Andhra Pradesh" },
  vijayawada: { lat: 16.5062, lon: 80.6480, state: "Andhra Pradesh" },
  guntur: { lat: 16.3067, lon: 80.4365, state: "Andhra Pradesh" },
  nellore: { lat: 14.4426, lon: 79.9865, state: "Andhra Pradesh" },
  tirupati: { lat: 13.6288, lon: 79.4192, state: "Andhra Pradesh" },

  // Tamil Nadu
  chennai: { lat: 13.0827, lon: 80.2707, state: "Tamil Nadu" },
  madras: { lat: 13.0827, lon: 80.2707, state: "Tamil Nadu" },
  coimbatore: { lat: 11.0168, lon: 76.9558, state: "Tamil Nadu" },
  madurai: { lat: 9.9252, lon: 78.1198, state: "Tamil Nadu" },
  salem: { lat: 11.6643, lon: 78.1460, state: "Tamil Nadu" },
  tiruchirappalli: { lat: 10.7905, lon: 78.7047, state: "Tamil Nadu" },
  trichy: { lat: 10.7905, lon: 78.7047, state: "Tamil Nadu" },

  // Kerala
  kochi: { lat: 9.9312, lon: 76.2673, state: "Kerala" },
  cochin: { lat: 9.9312, lon: 76.2673, state: "Kerala" },
  thiruvananthapuram: { lat: 8.5241, lon: 76.9366, state: "Kerala" },
  trivandrum: { lat: 8.5241, lon: 76.9366, state: "Kerala" },
  kozhikode: { lat: 11.2588, lon: 75.7804, state: "Kerala" },
  calicut: { lat: 11.2588, lon: 75.7804, state: "Kerala" },
  kollam: { lat: 8.8932, lon: 76.6141, state: "Kerala" },
  thrissur: { lat: 10.5276, lon: 76.2144, state: "Kerala" },

  // West Bengal / East
  kolkata: { lat: 22.5726, lon: 88.3639, state: "West Bengal" },
  calcutta: { lat: 22.5726, lon: 88.3639, state: "West Bengal" },
  howrah: { lat: 22.5958, lon: 88.2636, state: "West Bengal" },
  siliguri: { lat: 26.7271, lon: 88.3953, state: "West Bengal" },
  patna: { lat: 25.5941, lon: 85.1376, state: "Bihar" },
  ranchi: { lat: 23.3441, lon: 85.3096, state: "Jharkhand" },
  bhubaneswar: { lat: 20.2961, lon: 85.8245, state: "Odisha" },
  cuttack: { lat: 20.4625, lon: 85.8830, state: "Odisha" },
  guwahati: { lat: 26.1445, lon: 91.7362, state: "Assam" },
  shillong: { lat: 25.5788, lon: 91.8933, state: "Meghalaya" },
  imphal: { lat: 24.8170, lon: 93.9368, state: "Manipur" },
  agartala: { lat: 23.8315, lon: 91.2868, state: "Tripura" },

  // North / Central
  jaipur: { lat: 26.9124, lon: 75.7873, state: "Rajasthan" },
  jodhpur: { lat: 26.2389, lon: 73.0243, state: "Rajasthan" },
  udaipur: { lat: 24.5854, lon: 73.7125, state: "Rajasthan" },
  kota: { lat: 25.2138, lon: 75.8648, state: "Rajasthan" },
  lucknow: { lat: 26.8467, lon: 80.9462, state: "Uttar Pradesh" },
  kanpur: { lat: 26.4499, lon: 80.3319, state: "Uttar Pradesh" },
  agra: { lat: 27.1767, lon: 78.0081, state: "Uttar Pradesh" },
  varanasi: { lat: 25.3176, lon: 82.9739, state: "Uttar Pradesh" },
  meerut: { lat: 28.9845, lon: 77.7064, state: "Uttar Pradesh" },
  prayagraj: { lat: 25.4358, lon: 81.8463, state: "Uttar Pradesh" },
  indore: { lat: 22.7196, lon: 75.8577, state: "Madhya Pradesh" },
  bhopal: { lat: 23.2599, lon: 77.4126, state: "Madhya Pradesh" },
  jabalpur: { lat: 23.1815, lon: 79.9864, state: "Madhya Pradesh" },
  gwalior: { lat: 26.2183, lon: 78.1828, state: "Madhya Pradesh" },
  raipur: { lat: 21.2514, lon: 81.6296, state: "Chhattisgarh" },
  chandigarh: { lat: 30.7333, lon: 76.7794, state: "Chandigarh" },
  ludhiana: { lat: 30.9010, lon: 75.8573, state: "Punjab" },
  amritsar: { lat: 31.6340, lon: 74.8723, state: "Punjab" },
  jalandhar: { lat: 31.3260, lon: 75.5762, state: "Punjab" },
  dehradun: { lat: 30.3165, lon: 78.0322, state: "Uttarakhand" },
  shimla: { lat: 31.1048, lon: 77.1734, state: "Himachal Pradesh" },
  jammu: { lat: 32.7266, lon: 74.8570, state: "Jammu and Kashmir" },
  srinagar: { lat: 34.0837, lon: 74.7973, state: "Jammu and Kashmir" },

  // Goa
  panaji: { lat: 15.4909, lon: 73.8278, state: "Goa" },
  "panjim": { lat: 15.4909, lon: 73.8278, state: "Goa" },
  margao: { lat: 15.2832, lon: 73.9862, state: "Goa" },
  goa: { lat: 15.4909, lon: 73.8278, state: "Goa" },
};

export function normaliseCity(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

export function findCityCoordinate(value: string): CityCoordinate | null {
  const key = normaliseCity(value);
  if (!key) return null;
  return CITY_COORDINATES[key] ?? null;
}
