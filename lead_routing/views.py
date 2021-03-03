from django.shortcuts import render
from django.http import Http404
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core import serializers
from django.conf import settings
import json
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated

import os
import pandas as pd
import numpy as np
import re
from uszipcode import SearchEngine
import calendar
import pgeocode
from geopy.distance import great_circle
import joblib
from os import listdir
from os.path import isfile, join

# Create your views here.



def preprocess_df(df):
    df['date'] = pd.to_datetime(df['date'])
    df['move_date'] = pd.to_datetime(df['move_date'])
    df['date'] = df['date'].apply(lambda x: x.date())
    df['move_date'] = df['move_date'].apply(lambda x: x.date())
    df['date'] = pd.to_datetime(df['date'])
    df['move_date'] = pd.to_datetime(df['move_date'])

    try:
        df = df[(df['country'] != 'Spain') & (df['country'] != 'Canada')]
        df = df[(df['country2'] != 'Spain') & (df['country2'] != 'Canada') & (df['country2'] != 'Germany') & (df['country2'] != 'Lithuania') &
                (df['country2'] != 'Mexico') & (df['country2'] != 'Puerto Rico')]
    except:
        pass
    df = df[df['region'] != 'PR']
    df = df[df['region2'] != 'PR']
    df = df[df['postal_code'] != 'Eastvale']

    #Fixing the zipcodes with range
    df['postal_code'] = df['postal_code'].apply(lambda x: re.sub('[^0-9-]','',str(x)).split('-')[0])
    df['postal_code2'] = df['postal_code2'].apply(lambda x: re.sub('[^0-9-]','',str(x)).split('-')[0])

    #Fixing the zipcodes with less than 5 digit
    for i,row in df.iterrows():
      zc = str(row['postal_code'])
      n_zeroes = 5 - len(zc)
      for ii in range (0,n_zeroes):
        zc = '0'+str(row['postal_code'])
      df.at[i,'postal_code'] = zc

      zc = str(row['postal_code2'])
      n_zeroes = 5 - len(zc)
      for ii in range (0,n_zeroes):
        zc = '0'+str(row['postal_code2'])
      df.at[i,'postal_code2'] = zc


    #Filling up the missing REGIONS
    search = SearchEngine()
    missing_reg_df = df[pd.isna(df['region'])]
    for i, row in missing_reg_df.iterrows():
       reg = search.by_zipcode(row['postal_code']).to_dict()['state']
       df.at[i,'region'] = reg

    missing_reg_df = df[pd.isna(df['region2'])]
    for i, row in missing_reg_df.iterrows():
       reg = search.by_zipcode(row['postal_code']).to_dict()['state']
       df.at[i,'region2'] = reg

    #Deleting those rows with invalid postal codes
    #df = df[pd.notnull(df['region'])]
    df['region'].fillna(df['region2'],inplace=True)

    #Deleting the Country columns
    try:
        df.drop(['country','country2'],axis=1,inplace=True)
    except:
        pass
    df['interstate'] = df['region'] != df['region2']
    df['interstate'] = df['interstate'].apply(lambda x: 1 if x else 0)


    #Getting the coordinates from the postal codes of the source address
    coords = []
    coords2 = []
    ctr = 1
    nomi = pgeocode.Nominatim('us')
    for i, row in df.iterrows():
      try:
        rd = search.by_zipcode(row['postal_code']).to_dict()
        lon = ((rd['bounds_east'] - rd['bounds_west']) / 2) + rd['bounds_west']
        lat = ((rd['bounds_north'] - rd['bounds_south']) / 2) + rd['bounds_south']
      except:
        rd = nomi.query_postal_code(row['postal_code'])
        lat = rd['latitude']
        lon = rd['longitude']

      finally:
        coords.append(str(lat)+', '+str(lon))

      try:
        rd = search.by_zipcode(row['postal_code2']).to_dict()
        lon = ((rd['bounds_east'] - rd['bounds_west']) / 2) + rd['bounds_west']
        lat = ((rd['bounds_north'] - rd['bounds_south']) / 2) + rd['bounds_south']
      except:
        rd = nomi.query_postal_code(row['postal_code2'])
        lat = rd['latitude']
        lon = rd['longitude']

      finally:
        coords2.append(str(lat)+', '+str(lon))
        #print('rows remaining for getting coords: '+str(len(df)-ctr))
        ctr+=1

    df['address_coordinates'] = coords

    df['address_coordinates2'] = coords2

    #populating the missing distance column
    df_missing_dist = df[pd.isna(df['distance'])]
    for i,row in df_missing_dist.iterrows():
      if (row['address_coordinates'] == 'nan, nan') or (row['address_coordinates2'] == 'nan, nan'):
          df.at[i,'distance'] = 0
      else:
          p1 = (row['address_coordinates'].split(', ')[0], row['address_coordinates'].split(', ')[1])
          p2 = (row['address_coordinates2'].split(', ')[0], row['address_coordinates2'].split(', ')[1])
          gcdist = great_circle(p1,p2).miles
          df.at[i,'distance'] = gcdist

    #Populating missing move_to and move_from values to "not specified"
    df['move_from_type'].fillna('not specified',inplace=True)
    df['move_to_type'].fillna('not specified',inplace=True)

    #Populating missing first and last name with a blank
    df['first_name'].fillna('',inplace=True)
    df['last_name'].fillna('',inplace=True)
    df['email'].fillna('',inplace=True)
    #Filling missing post_partner_id with NA
    df['user_id'] = df['user_id'].apply(lambda x: str(x).split('.')[0] if '.' in str(x) else x)
    df['user_id'].fillna('NA',inplace=True)

    #Filling missing text_message with 0
    df['text_message'].fillna(0,inplace=True)


    df['distance_cat'] = df['distance'].apply(lambda x: '< 3 mi' if float(x)<3 else ('3 - 10 mi' if 3<=float(x)<10 else ('10 - 50 mi' if 10<=float(x)<50 else '> 50 mi')))


    df['date'] = pd.to_datetime(df['date'])
    df['move_date'] = pd.to_datetime(df['move_date'])
    df['date'] = df['date'].apply(lambda x: x.date())
    df['move_date'] = df['move_date'].apply(lambda x: x.date())
    df['days_away_from_move'] = (df['move_date']-df['date']).dt.days
    df['days_away_from_move'] = df['days_away_from_move'].astype(str)
    df['days_away_from_move'] = df['days_away_from_move'].astype(int)

    df['move_date < date'] = df['days_away_from_move'].apply(lambda x: 1 if x<0 else 0)

    #getting the Month of the move date
    df['date'] = pd.to_datetime(df['date'])
    df['move_date'] = pd.to_datetime(df['move_date'])
    df['move_date_month'] = df['move_date'].dt.month
    df['move_date_month'] = df['move_date_month'].apply(lambda x: calendar.month_name[x])

    #getting the week of the month of the move date
    df['day'] = df['move_date'].apply(lambda x: int(str(x.date()).split('-')[-1]))
    df['move_date_week'] = df['day'].apply(lambda x: 'first' if 0<x<=7 else ('second' if 7<x<=14 else ('third' if 14<x<=21 else 'last')))
    df.drop(['day'],axis=1,inplace=True)

    #getting the length of first and last name
    df['name_length'] = df['first_name']+df['last_name']
    df['name_length'] = df['name_length'].apply(lambda x: x.replace(' ',''))
    df['name_length'] = df['name_length'].str.len()

    #getting the length of email prefix
    df['email_length'] = df['email'].apply(lambda x: x.split('@')[0].strip())
    df['email_length'] = df['email_length'].str.len()

    return df

@api_view(["POST"])
@permission_classes((IsAuthenticated,))
print(os.getcwd())
def get_pred(data):
    cols = ['id','date','region','postal_code','country','region2','postal_code2','country2',
                     'distance','move_from_type','move_to_type','move_size','move_date','interstate',
                     'first_name','last_name','email','page_url','form_post_attempts','text_message',
                     'user_id','ping_partner_id','ping_payout']
    lst = []
    for i in cols:
        ele = json.loads(data.body)[i]
        if ele == '':
            ele = np.nan
        if i == 'distance':
            try:
                ele = float(ele)
            except:
                pass
            finally:
                lst.append(ele)
        elif (i == 'interstate') or (i == 'user_id') or (i == 'form_post_attempts'):
            try:
                ele = int(ele)
            except:
                pass
            finally:
                lst.append(ele)
        else:
            lst.append(ele)
    df = pd.DataFrame(lst)
    df = df.T
    df.columns = cols
    # df['distance'] = df['distance'].astype(float)
    # df['interstate'] = df['interstate'].astype(int)
    # df['user_id'] = df['user_id'].astype(int)
    # df['form_post_attempts'] = df['form_post_attempts'].astype(int)

    df_pred = preprocess_df(df)
    pid = df_pred['ping_partner_id'][0]
    payout = float(df_pred['ping_payout'][0])

    try:
        model = joblib.load(os.getcwd()+'/models/model_'+str(pid)+'.pkl')
    except Exception as E:
        return JsonResponse({'estimated_payout':payout}, safe=True)

    feats = ['region','move_from_type','move_to_type','move_size','interstate','form_post_attempts','user_id',
                  'distance','days_away_from_move','move_date < date','move_date_month','move_date_week',
                  'name_length','email_length','page_url','text_message']

    cat_feat = ['region','move_from_type','move_to_type','move_size','user_id','page_url','move_date_month',
                'move_date_week']
    for n in cat_feat:
        globals()[n] = joblib.load(os.getcwd()+'/objects/'+str(pid)+'/'+str(n)+'.pkl')
        globals()[n] = [str(i) for i in globals()[n]]
        df_pred[n] = df_pred[n].apply(lambda x: str(x) if str(x) in globals()[n] else 'others')
    x = df_pred[feats]
    x = pd.get_dummies(columns=cat_feat,drop_first=False, data=x)
    train_cols = joblib.load(os.getcwd()+'/objects/'+str(pid)+'/columns.pkl')
    missing_cols = set(train_cols) - set(x.columns)
    for c in missing_cols:
        x[c] = 0
    x = x[train_cols]
    y_pred_proba = model.predict_proba(x)
    y_pred_proba = [x[1] for x in y_pred_proba]
    df_pred['ping_return_probability'] = y_pred_proba
    df_pred['ping_payout'] = df_pred['ping_payout'].astype(float)
    df_pred['ping_estimated_payout'] = df_pred['ping_payout'] * (1-df_pred['ping_return_probability'])

    return JsonResponse({'estimated_payout':round(df_pred['ping_estimated_payout'][0],2)}, safe=True)


# def load_dfs(in_id):
#     df_leads = pd.read_csv(os.getcwd()+"/source_data/moving_leads (4).csv")
#     df_pings = pd.read_csv(os.getcwd()+"/source_data/ping_attempts.csv")
#     #df_posts = pd.read_csv(os.getcwd()+"/source_data/post_attempts (1).csv")
#     #df_posts['date'] = pd.to_datetime(df_posts['date'])
#     df_leads['date'] = pd.to_datetime(df_leads['date'])
#     df_leads = df_leads[df_leads['id'].isin(in_id)].reset_index(drop=True)
#     #df_leads = df_leads[df_leads['date'].dt.year.isin([2021])]
#
#     #df_leads = df_leads[(df_leads['id']>=129201) & (df_leads['id']<=129300)]
#
#     df_leads = df_leads[['id','date','region','postal_code','country','region2','postal_code2','country2',
#                          'distance','move_from_type','move_to_type','move_size','move_date','interstate',
#                          'first_name','last_name','email','page_url','form_post_attempts','text_message',
#                          'user_id','revenue']]
#     return (df_leads,df_pings)

#
#
# @api_view(["POST"])
# @permission_classes((IsAuthenticated,))
# def get_pred(data):
#     in_id = json.loads(data.body)['id']
#     in_id = [int(str(x).strip()) for x in in_id.split(',')]
#     df_leads,df_pings = load_dfs(in_id)
#     full_lead_ping = []
#
#     for i,row in df_leads.iterrows():
#         lead_ping = pd.DataFrame()
#         lead_info = pd.DataFrame(row)
#         lead_info = lead_info.T
#         ping_cols = ['id','date','payout','payout_equalizer','post_partner_id']
#         cur_lead_pings = df_pings[df_pings['moving_lead_id'] == row['id']]
#         cur_lead_pings = cur_lead_pings[ping_cols]
#         for i_ping,row_ping in cur_lead_pings.iterrows():
#             semi_lead_ping = lead_info.copy()
#             if row_ping['payout']>0:
#                 for col in ping_cols:
#                     semi_lead_ping['ping_'+col] = row_ping[col]
#                 lead_ping = lead_ping.append(semi_lead_ping)
#         if len(lead_ping)==0:
#             continue
#         cols = lead_ping.columns.tolist()
#         for ii, rows in lead_ping.iterrows():
#             full_lead_ping.append(rows.values.tolist())
#
#     full_lead_ping = pd.DataFrame(full_lead_ping)
#     if len(full_lead_ping)==0:
#         out = dict()
#         for iii in in_id:
#             out['iii'] = {}
#         return JsonResponse(out, safe=True)
#     else:
#         full_lead_ping.columns = cols
#
#     df_pred = preprocess_df(full_lead_ping)
#
#
#
#
#     files = [f for f in listdir(os.getcwd()+'/models/') if isfile(join(os.getcwd()+'/models/', f))]
#     files = [f for f in files if 'model' in f]
#     files = [f for f in files if 'score' not in f]
#     #pids = [int(f.split('_')[1].split('.')[0]) for f in files]
#     pids = df_pred['ping_post_partner_id'].unique().tolist()
#     feats = ['region','move_from_type','move_to_type','move_size','interstate','form_post_attempts','user_id',
#               'distance','days_away_from_move','move_date < date','move_date_month','move_date_week',
#               'name_length','email_length','page_url','text_message']
#     cat_feat = ['region','move_from_type','move_to_type','move_size','user_id','page_url','move_date_month',
#                 'move_date_week']
#     df_pred2 = df_pred.copy()
#     df_pred2.reset_index(drop=True,inplace=True)
#     df_pred3 = pd.DataFrame()
#     for pid in pids:
#         df_id = df_pred2[df_pred2['ping_post_partner_id']==pid]
#         try:
#             globals()['pipe_'+str(pid)] = joblib.load(os.getcwd()+'/models/model_'+str(pid)+'.pkl')
#             for n in cat_feat:
#                 globals()[n+'_'+str(pid)] = joblib.load(os.getcwd()+'/objects/'+str(pid)+'/'+str(n)+'.pkl')
#                 globals()[n+'_'+str(pid)] = [str(i) for i in globals()[n+'_'+str(pid)]]
#                 df_id[n] = df_id[n].apply(lambda x: str(x) if str(x) in globals()[n+'_'+str(pid)] else 'others')
#         except Exception as E:
#             print(E)
#             pass
#         finally:
#             df_pred3 = df_pred3.append(df_id)
#
#     df_pred3.sort_index(inplace=True)
#
#     df_pred2 = df_pred3.copy()
#     del df_pred3
#
#
#     df_pred3 = pd.DataFrame()
#     for pid in pids:
#         print(pid)
#         df_id = df_pred2[df_pred2['ping_post_partner_id']==pid]
#         try:
#             pipe = globals()['pipe_'+str(pid)]
#             x = df_id[feats]
#             x = pd.get_dummies(columns=cat_feat,drop_first=False, data=x)
#             train_cols = joblib.load(os.getcwd()+'/objects/'+str(pid)+'/columns.pkl')
#             missing_cols = set(train_cols) - set(x.columns)
#             for c in missing_cols:
#                 x[c] = 0
#             x = x[train_cols]
#             y_pred_proba = pipe.predict_proba(x)
#             y_pred_proba = [x[1] for x in y_pred_proba]
#             df_id['ping_return_probability'] = y_pred_proba
#             df_id['ping_estimated_payout'] = df_id['ping_payout'] * (1-df_id['ping_return_probability'])
#         except:
#             df_id['ping_return_probability'] = 0
#             df_id['ping_estimated_payout'] = df_id['ping_payout']
#         finally:
#             df_pred3 = df_pred3.append(df_id)
#
#
#     try:
#         df_pred3.drop(['Unnamed: 0'],inplace=True,axis=1)
#     except:
#         pass
#
#     df_pred3.sort_values(['id'],axis=0,inplace=True,ascending=True)
#     df_pred3.reset_index(inplace=True,drop=True)
#     df_final = df_pred3.copy()
#     out = dict()
#     for i in in_id:
#         semi_out = dict()
#         df_id = df_final[df_final['id']==i].sort_values(['ping_estimated_payout'],ascending=False).reset_index(drop=True)
#         df_id = df_id[['ping_post_partner_id','ping_payout','ping_return_probability','ping_estimated_payout']]
#         df_id.columns = ['partner_id','payout','return_probability','estimated_payout']
#         df_id['partner_id'] = df_id['partner_id'].apply(lambda x: str(x).split('.')[0])
#         df_id['return_probability'] = df_id['return_probability'].apply(lambda x: str(round(x*100,2))+'%')
#         df_id['estimated_payout'] = df_id['estimated_payout'].apply(lambda x: round(x,2))
#         for ii,row in df_id.iterrows():
#             semi_out[str(ii+1)] = row.to_dict()
#         out[str(i)] = semi_out
#     return JsonResponse(out, safe=True)




# @api_view(["POST"])
# @permission_classes((IsAuthenticated,))
# def IdealWeight(heightdata):
#     try:
#         height=json.loads(heightdata.body)
#         weight=str(height*10)
#         print(os.getcwd())
#
#         return JsonResponse("Ideal weight should be:"+weight+" kg",safe=False)
#     except ValueError as e:
#         return Response(e.args[0],status.HTTP_400_BAD_REQUEST)
