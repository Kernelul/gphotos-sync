#!/usr/bin/python
# coding: utf8
import os.path
import sqlite3 as lite
import shutil


# todo currently store full path in SyncFiles.Path
# would be better as relative path and store root once in global table
# this could be refreshed at start for a portable file system folder
# also this would remove the need to pass any paths to the GoogleMedia
# constructors (which is messy)
class LocalData:
    DB_FILE_NAME = 'gphotos.sql'
    BLOCK_SIZE = 10000
    EMPTY_FILE_NAME = 'etc/gphotos_empty.sqlite'
    VERSION = "1.4"

    class DuplicateDriveIdException(Exception):
        pass

    def __init__(self, root_folder):
        self.file_name = os.path.join(root_folder, LocalData.DB_FILE_NAME)
        if not os.path.exists(root_folder):
            os.mkdir(root_folder, 0o700)
        if not os.path.exists(self.file_name):
            self.setup_new_db()
        self.con = lite.connect(self.file_name)
        self.con.row_factory = lite.Row
        self.cur = self.con.cursor()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.con:
            self.store()
            self.con.close()

    def setup_new_db(self):
        print("creating new database")
        src_folder = os.path.dirname(os.path.abspath(__file__))
        from_file = os.path.join(src_folder, LocalData.EMPTY_FILE_NAME)
        shutil.copy(from_file, self.file_name)

    @classmethod
    def record_to_tuple(cls, rec):
        if rec:
            data_tuple = (
                rec['RemoteId'], rec['Url'], rec['Path'],
                rec['FileName'], rec['DuplicateNo'], rec['ModifyDate'],
                rec['Checksum'], rec['Description'], rec['FileSize'],
                rec['CreateDate'], rec['SyncDate'], rec['MediaType'],
                rec['SymLink']
            )
        else:
            data_tuple = None
        return data_tuple

    def get_files_by_search(self, drive_id='%', media_type='%',
                            start_date=None, end_date=None):

        params = (drive_id, int(media_type))
        # todo dates wont work since they are strings at present
        # need to be changed to INT
        date_clauses = ''
        if start_date:
            date_clauses += 'AND ExifDate >= ?'
            params += (start_date,)
        if start_date:
            date_clauses += 'AND ExifDate <= ?'
            params += (end_date,)

        query = "SELECT * FROM SyncFiles WHERE RemoteId LIKE ? AND "\
                " MediaType LIKE ? {0};".format(date_clauses)

        self.cur.execute(query, params)
        while True:
            records = self.cur.fetchmany(LocalData.BLOCK_SIZE)
            if not records:
                break
            for record in records:
                yield (self.record_to_tuple(record))

    def get_file_by_path(self, local_full_path):
        path = os.path.dirname(local_full_path)
        name = os.path.basename(local_full_path)
        self.cur.execute(
            "SELECT * FROM SyncFiles WHERE Path = ? AND FileName = ?;",
            (path, name))
        result = self.record_to_tuple(self.cur.fetchone())
        return result

    def put_file(self, data_tuple):
        try:
            self.cur.execute(
                "INSERT INTO SyncFiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ;",
                (None,) + data_tuple)
        except lite.IntegrityError as e:
            if 'RemoteId' in e.message:
                # this is an attempt add the same Drive file twice
                raise LocalData.DuplicateDriveIdException
            else:
                raise
        return self.cur.lastrowid

    def find_drive_file_ids(self, filename='%', exif_date='%', size='%',
                            use_create=False):
        if use_create:
            self.cur.execute(
                "SELECT Id FROM SyncFiles WHERE FileName LIKE ? AND "
                "CreateDate LIKE ? AND FileSize LIKE ?;",
                (filename, exif_date, size))
        else:
            self.cur.execute(
                "SELECT Id FROM SyncFiles WHERE FileName LIKE ? AND "
                "ModifyDate LIKE ? AND FileSize LIKE ?;",
                (filename, exif_date, size))
        res = self.cur.fetchall()

        if len(res) == 0:
            return None
        else:
            keys = [key['Id'] for key in res]
            return keys

    def get_album(self, table_id):
        self.cur.execute(
            "SELECT * FROM Albums WHERE Id = ?",
            (table_id,))
        results = self.cur.fetchone()
        for result in results:
            yield (result['AlbumId'], result['AlbumName'],
                   result['StartDate'], result['EndDate'])

    def put_album(self, album_id, album_name, start_date, end_end=0):
        self.cur.execute(
            "INSERT OR REPLACE INTO Albums(AlbumId, AlbumName, StartDate, "
            "EndDate) VALUES(?,?,?,?) ;",
            (album_id, unicode(album_name, 'utf8'), start_date, end_end))
        return self.cur.lastrowid

    def get_album_files(self, album_id='%'):
        self.cur.execute(
            "SELECT SyncFiles.Path, SyncFiles.Filename, Albums.AlbumName, "
            "Albums.EndDate FROM AlbumFiles "
            "INNER JOIN SyncFiles ON AlbumFiles.DriveRec=SyncFiles.Id "
            "INNER JOIN Albums ON AlbumFiles.AlbumRec=Albums.Id "
            "WHERE Albums.Id LIKE ?;",
            (album_id,))
        results = self.cur.fetchall()
        for result in results:
            yield (result)

        # # todo probably want a join on this with Albums and SyncFiles
        # # to get all the data required to make album file links in one query
        # self.cur.execute(
        #     "SELECT * FROM AlbumFiles WHERE Id = ?",
        #     (album_id,))
        # results = self.cur.fetchall()
        # for result in results:
        #     yield (result['AlbumRec'], result['DriveRec'])

    def put_album_file(self, album_rec, file_rec):
        self.cur.execute(
            "INSERT OR REPLACE INTO AlbumFiles(AlbumRec, DriveRec) VALUES(?,"
            "?) ;",
            (album_rec, file_rec))

    def store(self):
        print("\nSaving Database ...")
        self.con.commit()
        print("Database Saved.\n")
