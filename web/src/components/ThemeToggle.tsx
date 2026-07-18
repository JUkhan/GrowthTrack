import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Brightness4Icon from '@mui/icons-material/Brightness4'
import LightModeIcon from '@mui/icons-material/LightMode'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import { useThemeMode } from '../theme/ThemeModeContext'

function ThemeToggle() {
  const { preference, setPreference } = useThemeMode()

  return (
    <ToggleButtonGroup
      value={preference}
      exclusive
      onChange={(_event, next) => {
        if (next !== null) {
          setPreference(next)
        }
      }}
      aria-label="Theme"
    >
      <ToggleButton value="system" aria-label="System theme">
        <Brightness4Icon fontSize="small" />
      </ToggleButton>
      <ToggleButton value="light" aria-label="Light theme">
        <LightModeIcon fontSize="small" />
      </ToggleButton>
      <ToggleButton value="dark" aria-label="Dark theme">
        <DarkModeIcon fontSize="small" />
      </ToggleButton>
    </ToggleButtonGroup>
  )
}

export default ThemeToggle
