import pandas as pd
import json
directory = r'WHERE_WE_STORE_DATA'

#Load raw data
gc_history = pd.read_csv(directory+r'\league_h2h.csv')
otc = pd.read_csv(directory+r'\owner_team_concordance.csv')[['home_team','year','owner_1']].drop_duplicates()

#Create owner team concordance tables
home_owner = otc.rename(columns = {'owner_1':'home_owner'})
away_owner = otc.rename(columns = {'owner_1':'away_owner','home_team':'away_team'})
winner_owner = otc.rename(columns = {'owner_1':'winner_owner','home_team':'winner'})

#create franchise name table
franchise_name = otc.groupby('owner_1').max('year').reset_index()
franchise_name = otc.merge(franchise_name,how='inner',on=['owner_1','year'])
franchise_name['home_team'] = franchise_name['home_team'].apply(lambda x:x.replace(' ',''))

home_franchise = franchise_name[['home_team','owner_1']]\
    .rename(columns={'owner_1':'home_owner','home_team':'home_franchise'})
away_franchise = franchise_name[['home_team','owner_1']]\
    .rename(columns={'owner_1':'away_owner','home_team':'away_franchise'})
winner_franchise = franchise_name[['home_team','owner_1']]\
    .rename(columns={'owner_1':'winner_owner','home_team':'winner_franchise'})

#Standardise franchise names
franchise_history = gc_history\
    .merge(home_owner,on = ['home_team','year'],copy=False)\
    .merge(away_owner,on = ['away_team','year'],copy=False)\
    .merge(winner_owner,on = ['winner','year'],copy=False)\
    .sort_values(by=['year','round','game'])[['year','round','game','home_score','away_score',
                                              'home_owner','away_owner','winner_owner']]\
    .merge(home_franchise,on = ['home_owner'],copy=False)\
    .merge(away_franchise,on = ['away_owner'],copy=False)\
    .merge(winner_franchise,on = ['winner_owner'],copy=False)\
    .sort_values(by=['year','round','game'])



#Define function that converts franchise history into head-2-head records
def calculate_history(team_name= 'ThePuffins',input_data=franchise_history,start_year=2012):
   
    input_data = franchise_history.loc[((franchise_history['home_franchise']==team_name)|
                                       (franchise_history['away_franchise']==team_name))&
                                       (franchise_history['year']>=start_year),:]
    #Set base franchise
    input_data['baseFranchise'] = team_name
    
    #Set opponent column
    input_data['opponent'] = input_data[['home_franchise','away_franchise']]\
        .apply(lambda x: x[0] if x[0]!=team_name else x[1],axis=1)
    
    #Set base points
    input_data['basePoints'] = input_data[['home_franchise','away_franchise','home_score','away_score']]\
    .apply(lambda x: x[2] if x[0]==team_name else x[3],axis=1)
    
    #Set opponent points
    input_data['opponentPoints'] = input_data[['home_franchise','away_franchise','home_score','away_score']]\
    .apply(lambda x: x[2] if x[0]!=team_name else x[3],axis=1)
    
    #calculate results
    input_data['wins']=input_data['winner_franchise'].apply(lambda x: 1 if x == team_name else 0)
    input_data['losses']=input_data[['winner_franchise','home_score','away_score']]\
        .apply(lambda x: 1 if (x[0] != team_name)&(x[1]!=x[2]) else 0,axis=1)
    input_data['draws']=input_data[['home_score','away_score']]\
        .apply(lambda x: 1 if (x[0]==x[1]) else 0,axis=1)
    input_data = input_data[['baseFranchise','opponent','wins','losses','draws','basePoints','opponentPoints']]
    
    #Aggregate records
    output_data = input_data.groupby(['opponent']).sum().reset_index()
    
    #Collect overall record
    overall = input_data.copy()
    overall['opponent']='All'
    overall = overall.groupby(['opponent']).sum().reset_index()
    
    #concatenate h2h and overall record
    output_data = pd.concat([output_data,overall],axis=0)
    output_data['winPercentage'] = (output_data['wins']+output_data['draws']*.5)/\
                                   (output_data['wins']+output_data['draws']+output_data['losses'])
    output_data['winPercentage']=(output_data['winPercentage']*100).astype(str).apply(lambda x: x[0:2]+'%')
    
    #Add additional columns
    output_data['gamesPlayed']=(output_data['wins']+output_data['draws']+output_data['losses'])
    output_data['record'] = output_data['wins'].astype(str)+'-'+\
                            output_data['losses'].astype(str)+'-'+\
                            output_data['draws'].astype(str)
    
    return (output_data.loc[output_data['opponent']!='All',['opponent','record','winPercentage','basePoints','opponentPoints','gamesPlayed']],
            output_data.loc[output_data['opponent']=='All',['record','winPercentage','basePoints','opponentPoints','gamesPlayed']])

  
#iterate trhrough franchise to create dictionary object, convert to json and store
h2h_dictionary ={}
for t in franchise_name['home_team']:
    h2h_dictionary[t]={'opponentHistory':calculate_history(t)[0].to_dict(orient='records'),
                  'allTimeRecord':calculate_history(t)[1].to_dict(orient='records')[0]}

with open(directory+r"\league_records.json", "w") as outfile:
    json.dump(h2h_dictionary, outfile,indent = 4)

outfile.close()
#franchise_history
