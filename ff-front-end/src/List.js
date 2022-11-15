import * as React from "react";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import ListItemAvatar from "@mui/material/ListItemAvatar";
import Avatar from "@mui/material/Avatar";
import SportsFootballIcon from "@mui/icons-material/SportsFootball";

export default function OpponentList({ teamName, records }) {
  return (
    teamName &&
    records[teamName]["opponentHistory"].map((entry) => {
      return (
        <List
          sx={{ width: "100%", maxWidth: 360, bgcolor: "background.paper" }}
        >
          <ListItem>
            <ListItemAvatar>
              <Avatar>
                <SportsFootballIcon />
              </Avatar>
            </ListItemAvatar>
            <ListItemText primary={entry.opponent} secondary={entry.record} />
          </ListItem>
        </List>
      );
    })
  );
}
