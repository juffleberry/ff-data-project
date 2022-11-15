import OpponentList from "./List";
import records from "./league_records.json";
import { useState } from "react";
import { FormControl, InputLabel, Select, MenuItem } from "@mui/material";

function App() {
  const [currentTeamName, setCurrentTeamName] = useState("");

  const handleChange = (event) => {
    setCurrentTeamName(event.target.value);
  };

  return (
    <div className="App">
      <FormControl fullWidth>
        <InputLabel id="team-select-label">Team</InputLabel>
        <Select
          labelId="team-select-label"
          value={currentTeamName}
          label="Team"
          onChange={handleChange}
        >
          {Object.keys(records).map((teamName) => {
            return <MenuItem value={teamName}>{teamName}</MenuItem>;
          })}
        </Select>
      </FormControl>
      <OpponentList teamName={currentTeamName} records={records} />
    </div>
  );
}

export default App;
