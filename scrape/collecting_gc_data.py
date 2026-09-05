# ARCHIVED — this no longer runs, and there is nothing left for it to scrape.
#
# NFL shut its fantasy product down; fantasy.nfl.com/league/<id>/history/... now
# redirects to a news page. Selenium also removed the `executable_path` argument
# in 4.10, so the driver setup below is dead on its own terms.
#
# Kept because it documents where data/league_h2h.csv came from.

#Load packages
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager .chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import pandas as pd
from time import sleep

driver = webdriver.Chrome(executable_path=ChromeDriverManager().install())

#credentials
username = 'USER_EMAIL'
password = 'PASSWORD'

#Pass credentials
driver.get('https://id.nfl.com/account/sign-in')
inputs = driver.find_elements(By.TAG_NAME,'input')
inputs[0].send_keys(username)
inputs[1].send_keys(password)
sign_in = driver.find_elements(By.CLASS_NAME,"css-1dbjc4n")
sign_in = [s for s in sign_in if s.text == 'Sign In'][0]
a = ActionChains(driver).move_to_element(sign_in).double_click()
a.perform()

# Get aribrary round (For some reason the first time you get this link after logging in, NFL
# redirects you
sleep(5)
driver.get('https://fantasy.nfl.com/league/1078038/history/2022/teamgamecenter?teamId=1&week=8')
sleep(5)

#Collect data as dictionary
main_dict = {}
for year in range(2012,2023):
    round_dict={}
    for round in range(1,17):
        games_details = []
        #loop in case page doesnt load properly (games_details will be empty in this case)
        for check in range(0,100):
            if len(games_details)>0: break
            else: pass
            driver.get('https://fantasy.nfl.com/league/1078038/history/{year}/teamgamecenter?teamId=1&week={round}'.format(year=year,round=round))
            sleep(.1*check)
            games_dict ={}
            games = driver.find_elements(By.CLASS_NAME,'dynamic')
            games_details = [s.find_elements(By.TAG_NAME,'div') for s in games][0:8]
        i=0
        for g in games_details:
            try:
                detail_dict = {'year':year,
                               'round':round,
                               'game':i+1,
                               'home_team':g[0].find_element(By.TAG_NAME,'em').text,
                               'away_team':g[1].find_element(By.TAG_NAME,'em').text,
                               'home_score':g[0].find_element(By.TAG_NAME,'span').text,
                               'away_score':g[1].find_element(By.TAG_NAME,'span').text
                              }
                main_dict[str(year)+'_'+str(round)+'_'+str(i+1)] = detail_dict
            except:
                pass
            
            i+=1
  
table_data = pd.DataFrame.from_dict(main_dict).transpose()
dataset = table_data[['home_team','away_team','home_score','away_score']]
table_data['winner'] = dataset.apply(lambda x: x[0] if float(x[2])>float(x[3]) else x[1],axis = 1)
table_data.to_csv('CSV_PATH')
