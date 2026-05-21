/**
 * 天气工具 - 使用 wttr.in 免费 API
 */

// 天气图标映射
const WEATHER_ICONS = {
  'Sunny': '☀️',
  'Clear': '🌙',
  'Partly cloudy': '⛅',
  'Cloudy': '☁️',
  'Overcast': '☁️',
  'Mist': '🌫️',
  'Fog': '🌫️',
  'Light rain': '🌧️',
  'Medium rain': '🌧️',
  'Heavy rain': '🌧️',
  'Light drizzle': '🌦️',
  'Patchy rain possible': '🌦️',
  'Light snow': '🌨️',
  'Medium snow': '🌨️',
  'Heavy snow': '❄️',
  'Thundery outbreaks possible': '⛈️',
  'Blowing snow': '🌨️',
  'Blizzard': '❄️',
  'default': '🌤️'
}

/**
 * 获取天气图标
 */
function getWeatherIcon(weatherDesc) {
  if (!weatherDesc) return WEATHER_ICONS.default
  for (const [key, icon] of Object.entries(WEATHER_ICONS)) {
    if (weatherDesc.toLowerCase().includes(key.toLowerCase())) {
      return icon
    }
  }
  return WEATHER_ICONS.default
}

/**
 * 获取当前天气
 * @returns {Promise<{city: string, temp: string, icon: string, desc: string}>}
 */
export async function getCurrentWeather() {
  try {
    const response = await fetch(`https://wttr.in/?format=j1`, {
      headers: {
        'Accept': 'application/json'
      }
    })
    const data = await response.json()

    if (data && data.current_condition && data.current_condition[0]) {
      const current = data.current_condition[0]
      return {
        city: data.nearest_area?.[0]?.areaName?.[0]?.value || '未知',
        temp: current.temp_C + '°C',
        icon: getWeatherIcon(current.weatherDesc?.[0]?.value),
        desc: current.weatherDesc?.[0]?.value || ''
      }
    }
    return null
  } catch (error) {
    console.error('Failed to fetch weather:', error)
    return null
  }
}

/**
 * 根据城市名获取天气
 * @param {string} city - 城市名
 * @returns {Promise<{city: string, temp: string, icon: string, desc: string}>}
 */
export async function getWeatherByCity(city) {
  try {
    const response = await fetch(`https://wttr.in/${encodeURIComponent(city)}?format=j1`, {
      headers: {
        'Accept': 'application/json'
      }
    })
    const data = await response.json()

    if (data && data.current_condition && data.current_condition[0]) {
      const current = data.current_condition[0]
      return {
        city: data.nearest_area?.[0]?.areaName?.[0]?.value || city,
        temp: current.temp_C + '°C',
        icon: getWeatherIcon(current.weatherDesc?.[0]?.value),
        desc: current.weatherDesc?.[0]?.value || ''
      }
    }
    return null
  } catch (error) {
    console.error('Failed to fetch weather:', error)
    return null
  }
}
